"""
FastAPI web interface for RAG query testing.

Provides a REST API and web UI for real-time RAG queries with conversation threading.
"""

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api.admin.audit_logger import AdminAuditLogger
from src.api.admin.backup_manager import BackupManager
from src.api.admin.document_manager import DocumentManager
from src.api.admin.whitelist_manager import WhitelistManager
from src.api.auth import (
    OTPManager,
    Session,
    SessionManager,
    get_session_id,
    set_session_cookie,
)

# Import all models from models module
from src.api.models import (
    AdminActionResponse,
    CrawledUrlResponse,
    CrawlRequest,
    DocumentListResponse,
    FeedbackAnalyticsResponse,
    StatsResponse,
    TopicClusteringResponse,
    UsageAnalyticsResponse,
    UserQueriesResponse,
    WhitelistEntryRequest,
    WhitelistResponse,
)
from src.api.routes.auth import create_auth_router
from src.api.routes.conversations import create_conversations_router
from src.api.routes.feedback import create_feedback_router
from src.api.routes.query import create_query_router
from src.config import settings
from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.email.conversation_manager import (
    MessageType,
    conversation_manager,
)
from src.email.email_sender import EmailSender
from src.email.whitelist_validator import WhitelistValidator
from src.rag.query_handler import QueryHandler
from src.rag.rag_engine import get_system_prompt

logger = logging.getLogger(__name__)


# ============================================================================
# Authentication & Session Management
# ============================================================================
# Note: Session, SessionManager, and OTPManager are now in src/api/auth/
# These are imported above and instantiated below.


# Initialize components
app = FastAPI(
    title=f"{settings.instance_name} API",
    description=settings.instance_description,
    version="1.0.0",
)

# Configure CORS to allow reverse proxy access
# This is essential for WebSocket/Socket.IO connections through reverse proxies
# Note: When allow_credentials=True, allow_origins cannot be ["*"]
# We must specify exact origins or use allow_origin_regex
if settings.allowed_origins == "*":
    # For development: allow all origins with regex
    logger.warning(
        "CORS configured with wildcard (*). This is insecure for production. "
        "Set ALLOWED_ORIGINS to specific domains."
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex="https?://.*",  # Allow any origin (dev only)
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Production: specific origins only
    allowed_origins = [origin.strip() for origin in settings.allowed_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

session_manager = SessionManager(session_timeout=settings.web_session_timeout)
query_handler = QueryHandler()
otp_manager = OTPManager()
email_sender = EmailSender()

# Initialize whitelist validators for authentication
query_whitelist = WhitelistValidator(
    whitelist_file=settings.email_query_whitelist_file,
    whitelist=settings.email_query_whitelist,
    enabled=settings.email_query_whitelist_enabled,
)

teach_whitelist = WhitelistValidator(
    whitelist_file=settings.email_teach_whitelist_file,
    whitelist=settings.email_teach_whitelist,
    enabled=settings.email_teach_whitelist_enabled,
)

admin_whitelist = WhitelistValidator(
    whitelist_file=settings.email_admin_whitelist_file,
    whitelist=settings.email_admin_whitelist,
    enabled=settings.email_admin_whitelist_enabled,
)

# Mapping of whitelist types to validators for dynamic reloading
whitelist_validators = {
    "queriers": query_whitelist,
    "teachers": teach_whitelist,
    "admins": admin_whitelist,
}

# Initialize admin managers
kb_manager = KnowledgeBaseManager()
document_processor = DocumentProcessor()
whitelist_manager = WhitelistManager()
document_manager = DocumentManager(
    kb_manager=kb_manager,
    document_processor=document_processor,
)
audit_logger = AdminAuditLogger()
backup_manager = BackupManager()

# Setup static files directory (needed by feedback router)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)

# Setup auth router (can be done early, doesn't need require_auth)
auth_router = create_auth_router(
    session_manager=session_manager,
    otp_manager=otp_manager,
    query_whitelist=query_whitelist,
    admin_whitelist=admin_whitelist,
    email_sender=email_sender,
    get_session_id=get_session_id,
    set_session_cookie=set_session_cookie,
    settings=settings,
)

# Include auth router
app.include_router(auth_router)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Setup templates (using same directory as static for HTML templates)
templates = Jinja2Templates(directory=str(static_dir))


# Version information
def get_version() -> str:
    """Get version string combining package version and git commit."""
    import subprocess

    base_version = "0.1.0"  # From pyproject.toml
    try:
        # Get git commit hash
        git_hash = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=Path(__file__).parent.parent.parent,
            )
            .decode()
            .strip()
        )
        return f"{base_version}+{git_hash}"
    except Exception:
        return base_version


# Helper functions
# Note: get_session_id and set_session_cookie moved to src/api/auth/dependencies.py


async def cleanup_old_attachments():
    """Background task to cleanup old attachment files."""
    temp_dir = settings.email_temp_dir
    if not temp_dir.exists():
        return

    now = datetime.now()
    cutoff = now - timedelta(hours=1)  # Delete files older than 1 hour

    try:
        for session_dir in temp_dir.glob("web_*"):
            if not session_dir.is_dir():
                continue

            # Check directory modification time
            mtime = datetime.fromtimestamp(session_dir.stat().st_mtime)
            if mtime < cutoff:
                import shutil

                shutil.rmtree(session_dir)
                logger.info(f"Cleaned up old attachment directory: {session_dir.name}")
    except Exception as e:
        logger.error(f"Error during attachment cleanup: {e}")


# Authentication dependency
# Note: send_otp_email moved to routes/auth.py
async def require_auth(request: Request) -> Session:
    """
    Dependency to require authentication for endpoints.

    Args:
        request: FastAPI request object

    Returns:
        Authenticated session

    Raises:
        HTTPException: If not authenticated
    """
    session_id = get_session_id(request)
    if not session_id:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login first.",
        )

    session = session_manager.get_session(session_id)
    if not session or not session.is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login first.",
        )

    # Update last activity
    session.last_activity = datetime.now()

    return session


async def require_admin(request: Request) -> Session:
    """
    Dependency to require admin privileges for endpoints.

    Args:
        request: FastAPI request object

    Returns:
        Authenticated admin session

    Raises:
        HTTPException: If not authenticated or not an admin
    """
    # First check authentication
    session = await require_auth(request)

    # Then check admin status
    if not session.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Forbidden. Admin privileges required.",
        )

    return session


# Setup routers that depend on require_auth
feedback_router = create_feedback_router(
    conversation_manager=conversation_manager,
    static_dir=static_dir,
    require_auth=require_auth,
)

conversations_router = create_conversations_router(
    conversation_manager=conversation_manager,
    session_manager=session_manager,
    require_auth=require_auth,
)

query_router = create_query_router(
    query_handler=query_handler,
    conversation_manager=conversation_manager,
    session_manager=session_manager,
    settings=settings,
    require_auth=require_auth,
    set_session_cookie=set_session_cookie,
    cleanup_old_attachments=cleanup_old_attachments,
)

# Include routers
app.include_router(feedback_router)
app.include_router(conversations_router)
app.include_router(query_router)


# API Endpoints
# Note: Authentication endpoints moved to routes/auth.py
# Note: Feedback endpoints moved to routes/feedback.py
# Note: Conversation endpoints moved to routes/conversations.py
# Note: Query endpoints moved to routes/query.py


# Protected Endpoints (require authentication)
@app.get("/")
async def root(request: Request):
    """
    Serve main web interface.

    Redirects to login page if user is not authenticated.
    """
    # Check authentication
    session_id = get_session_id(request)
    if not session_id:
        return RedirectResponse(url="/static/login.html", status_code=303)

    session = session_manager.get_session(session_id)
    if not session or not session.is_authenticated():
        return RedirectResponse(url="/static/login.html", status_code=303)

    # User is authenticated, serve the chat interface
    index_file = static_dir / "index.html"
    if index_file.exists():
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "instance_name": settings.instance_name,
                "instance_description": settings.instance_description,
                "organization": settings.organization or "",
                "version": get_version(),
            },
        )
    return {"message": f"Welcome to {settings.instance_name} API", "docs": "/docs"}


@app.get("/admin")
async def admin_panel(request: Request):
    """
    Serve admin panel interface.

    Requires authentication and admin privileges.
    Redirects to login if not authenticated or to main page if not admin.
    """
    # Check authentication
    session_id = get_session_id(request)
    if not session_id:
        return RedirectResponse(url="/static/login.html", status_code=303)

    session = session_manager.get_session(session_id)
    if not session or not session.is_authenticated():
        return RedirectResponse(url="/static/login.html", status_code=303)

    # Check admin privileges
    if not session.is_admin:
        # Authenticated but not admin - redirect to main chat
        return RedirectResponse(url="/", status_code=303)

    # User is authenticated and admin, serve the admin panel
    admin_file = static_dir / "admin.html"
    if admin_file.exists():
        return templates.TemplateResponse(
            "admin.html",
            {
                "request": request,
                "instance_name": settings.instance_name,
                "version": get_version(),
            },
        )
    raise HTTPException(status_code=404, detail="Admin panel not found")


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get knowledge base statistics.

    Returns:
        StatsResponse with KB stats
    """
    try:
        stats = query_handler.get_stats()
        # Extract just filenames from document dicts
        documents = stats.get("documents", [])
        document_names = [
            doc.get("filename", "Unknown") if isinstance(doc, dict) else str(doc)
            for doc in documents
        ]
        return StatsResponse(
            total_chunks=stats.get("total_chunks", 0),
            unique_documents=stats.get("unique_documents", 0),
            documents=document_names,
        )
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return StatsResponse(total_chunks=0, unique_documents=0, documents=[])


# Admin Endpoints
@app.get("/api/admin/whitelists/{whitelist_type}", response_model=WhitelistResponse)
async def get_whitelist(
    whitelist_type: str,
    session: Session = Depends(require_admin),
):
    """
    Get whitelist entries.

    Requires admin privileges.

    Args:
        whitelist_type: Type of whitelist (queriers, teachers, admins)
        session: Admin session (injected by dependency)

    Returns:
        WhitelistResponse with entries

    Raises:
        HTTPException: If whitelist type is invalid
    """
    try:
        data = whitelist_manager.read_whitelist(whitelist_type)
        logger.info(
            f"Admin {session.email} read {whitelist_type} whitelist "
            f"({len(data['entries'])} entries)"
        )
        return WhitelistResponse(
            entries=data["entries"],
            whitelist_type=whitelist_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error reading whitelist {whitelist_type}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error reading whitelist: {str(e)}"
        )


@app.post(
    "/api/admin/whitelists/{whitelist_type}/add", response_model=AdminActionResponse
)
async def add_whitelist_entry(
    whitelist_type: str,
    request: WhitelistEntryRequest,
    session: Session = Depends(require_admin),
):
    """
    Add entry to whitelist.

    Requires admin privileges.

    Args:
        whitelist_type: Type of whitelist (queriers, teachers, admins)
        request: Entry to add
        session: Admin session (injected by dependency)

    Returns:
        AdminActionResponse with success status

    Raises:
        HTTPException: If entry is invalid or operation fails
    """
    try:
        added = whitelist_manager.add_entry(whitelist_type, request.entry)

        # Reload the corresponding validator to pick up changes
        if whitelist_type in whitelist_validators:
            whitelist_validators[whitelist_type].reload()
            logger.debug(f"Reloaded {whitelist_type} whitelist validator")

        # Log the action
        audit_logger.log_whitelist_add(
            session.email,
            whitelist_type,
            request.entry,
            success=True,
        )

        message = (
            f"Entry '{request.entry}' added to {whitelist_type} whitelist"
            if added
            else f"Entry '{request.entry}' already exists in {whitelist_type} whitelist"
        )

        logger.info(f"Admin {session.email}: {message}")

        return AdminActionResponse(
            success=True,
            message=message,
            details={"entry": request.entry, "was_new": added},
        )

    except ValueError as e:
        audit_logger.log_whitelist_add(
            session.email,
            whitelist_type,
            request.entry,
            success=False,
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        audit_logger.log_whitelist_add(
            session.email,
            whitelist_type,
            request.entry,
            success=False,
        )
        logger.error(f"Error adding to whitelist {whitelist_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding entry: {str(e)}")


@app.delete(
    "/api/admin/whitelists/{whitelist_type}/remove", response_model=AdminActionResponse
)
async def remove_whitelist_entry(
    whitelist_type: str,
    request: WhitelistEntryRequest,
    session: Session = Depends(require_admin),
):
    """
    Remove entry from whitelist.

    Requires admin privileges.

    Args:
        whitelist_type: Type of whitelist (queriers, teachers, admins)
        request: Entry to remove
        session: Admin session (injected by dependency)

    Returns:
        AdminActionResponse with success status

    Raises:
        HTTPException: If entry not found or operation fails
    """
    try:
        removed = whitelist_manager.remove_entry(whitelist_type, request.entry)

        # Reload the corresponding validator to pick up changes
        if whitelist_type in whitelist_validators:
            whitelist_validators[whitelist_type].reload()
            logger.debug(f"Reloaded {whitelist_type} whitelist validator")

        # Log the action
        audit_logger.log_whitelist_remove(
            session.email,
            whitelist_type,
            request.entry,
            success=True,
        )

        message = (
            f"Entry '{request.entry}' removed from {whitelist_type} whitelist"
            if removed
            else f"Entry '{request.entry}' not found in {whitelist_type} whitelist"
        )

        logger.info(f"Admin {session.email}: {message}")

        return AdminActionResponse(
            success=True,
            message=message,
            details={"entry": request.entry, "was_removed": removed},
        )

    except ValueError as e:
        audit_logger.log_whitelist_remove(
            session.email,
            whitelist_type,
            request.entry,
            success=False,
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        audit_logger.log_whitelist_remove(
            session.email,
            whitelist_type,
            request.entry,
            success=False,
        )
        logger.error(f"Error removing from whitelist {whitelist_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Error removing entry: {str(e)}")


@app.get("/api/admin/documents", response_model=DocumentListResponse)
async def list_documents(
    session: Session = Depends(require_admin),
):
    """
    List all documents in knowledge base.

    Requires admin privileges.

    Args:
        session: Admin session (injected by dependency)

    Returns:
        DocumentListResponse with document list
    """
    try:
        documents = document_manager.list_documents()
        logger.info(f"Admin {session.email} listed documents ({len(documents)} found)")
        return DocumentListResponse(
            documents=documents,
            total_count=len(documents),
        )
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error listing documents: {str(e)}"
        )


@app.get("/api/admin/documents/descriptions")
async def get_document_descriptions(
    session: Session = Depends(require_admin),
):
    """
    Get AI-generated descriptions for all documents.

    Requires admin privileges.

    Args:
        session: Admin session (injected by dependency)

    Returns:
        List of document descriptions
    """
    try:
        from src.document_processing.description_generator import description_generator

        descriptions = description_generator.get_all_descriptions()
        logger.info(
            f"Admin {session.email} retrieved {len(descriptions)} document descriptions"
        )
        return {
            "descriptions": descriptions,
            "total_count": len(descriptions),
        }
    except Exception as e:
        logger.error(f"Error retrieving document descriptions: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving descriptions: {str(e)}"
        )


@app.delete("/api/admin/documents/{file_hash}", response_model=AdminActionResponse)
async def delete_document(
    file_hash: str,
    archive: bool = True,
    session: Session = Depends(require_admin),
):
    """
    Delete document from knowledge base.

    Requires admin privileges.

    Args:
        file_hash: SHA-256 hash of document to delete
        archive: Whether to archive the file (default: True)
        session: Admin session (injected by dependency)

    Returns:
        AdminActionResponse with deletion details

    Raises:
        HTTPException: If document not found or operation fails
    """
    try:
        result = document_manager.delete_document(file_hash, archive=archive)

        # Log the action
        audit_logger.log_document_delete(
            session.email,
            result["filename"],
            file_hash,
            success=True,
        )

        message = (
            f"Document '{result['filename']}' deleted "
            f"({'archived' if result['archived'] else 'permanently removed'}). "
            f"{result['chunks_removed']} chunks removed from KB."
        )

        logger.info(f"Admin {session.email}: {message}")

        return AdminActionResponse(
            success=True,
            message=message,
            details=result,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        audit_logger.log_document_delete(
            session.email,
            f"hash:{file_hash}",
            file_hash,
            success=False,
        )
        logger.error(f"Error deleting document {file_hash}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting document: {str(e)}"
        )


@app.get("/api/admin/documents/{file_hash}/view")
async def view_document(
    file_hash: str,
    session: Session = Depends(require_admin),
):
    """
    View the text content of a document from the knowledge base.

    Requires admin privileges.

    Args:
        file_hash: SHA-256 hash of document to view
        session: Admin session (injected by dependency)

    Returns:
        JSON with document content and metadata

    Raises:
        HTTPException: If document not found
    """
    try:
        # Get document info
        documents = document_manager.list_documents()
        doc = next((d for d in documents if d.get("file_hash") == file_hash), None)

        if not doc:
            raise HTTPException(
                status_code=404, detail=f"Document not found with hash: {file_hash}"
            )

        # Get content from KB
        content = kb_manager.get_document_content(file_hash)

        if not content:
            raise HTTPException(
                status_code=404,
                detail=f"No content found for document: {doc['filename']}",
            )

        # Log the view action
        audit_logger.log_action(
            session.email,
            "document_view",
            doc["filename"],
            "success",
            f"hash:{file_hash}",
        )

        logger.info(f"Admin {session.email} viewed document: {doc['filename']}")

        return {
            "success": True,
            "filename": doc["filename"],
            "file_hash": file_hash,
            "source_type": doc.get("source_type"),
            "file_type": doc.get("file_type"),
            "content": content,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing document {file_hash}: {e}")
        raise HTTPException(status_code=500, detail=f"Error viewing document: {str(e)}")


@app.get("/api/admin/documents/{file_hash}/download")
async def download_document(
    file_hash: str,
    session: Session = Depends(require_admin),
):
    """
    Download a document file from the knowledge base.

    Requires admin privileges.

    Args:
        file_hash: SHA-256 hash of document to download
        session: Admin session (injected by dependency)

    Returns:
        File download response

    Raises:
        HTTPException: If document not found or file doesn't exist
    """
    try:
        # Get document info
        documents = document_manager.list_documents()
        doc = next((d for d in documents if d.get("file_hash") == file_hash), None)

        if not doc:
            raise HTTPException(
                status_code=404, detail=f"Document not found with hash: {file_hash}"
            )

        # Only allow download of file-sourced documents (manual uploads or file ingestion)
        # Email-sourced documents don't have physical files to download
        allowed_source_types = ["manual", "file"]
        if doc.get("source_type") not in allowed_source_types:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot download documents from source type: {doc.get('source_type')}. Only manual/file uploads can be downloaded.",
            )

        filename = doc["filename"]
        file_path = document_manager.documents_path / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")

        # Log the download action
        audit_logger.log_action(
            session.email, "document_download", filename, "success", f"hash:{file_hash}"
        )

        logger.info(f"Admin {session.email} downloaded document: {filename}")

        # Determine content type based on file extension
        content_type = "application/octet-stream"
        if filename.endswith(".pdf"):
            content_type = "application/pdf"
        elif filename.endswith(".docx"):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif filename.endswith(".doc"):
            content_type = "application/msword"
        elif filename.endswith(".txt"):
            content_type = "text/plain"
        elif filename.endswith(".csv"):
            content_type = "text/csv"

        return FileResponse(
            file_path,
            media_type=content_type,
            filename=filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading document {file_hash}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error downloading document: {str(e)}"
        )


@app.post("/api/admin/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    session: Session = Depends(require_admin),
):
    """
    Upload and process a document into the knowledge base.

    Requires admin privileges.

    Args:
        file: The file to upload
        session: Admin session (injected by dependency)

    Returns:
        JSON with upload status and processing details

    Raises:
        HTTPException: If upload fails or file type is unsupported
    """
    try:
        # Validate file type
        allowed_extensions = {".pdf", ".docx", ".doc", ".txt", ".csv"}
        file_ext = Path(file.filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Allowed: {', '.join(allowed_extensions)}",
            )

        # Create temp directory if it doesn't exist
        temp_dir = Path(settings.email_temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Save uploaded file to temp location
        temp_file_path = temp_dir / f"upload_{uuid.uuid4().hex}_{file.filename}"

        try:
            # Read and save file
            content = await file.read()
            with open(temp_file_path, "wb") as f:
                f.write(content)

            logger.info(f"Saved uploaded file to: {temp_file_path}")

            # Save permanent copy to kb/documents/ first
            documents_dir = settings.kb_documents_path
            documents_dir.mkdir(parents=True, exist_ok=True)

            # Check if file already exists
            permanent_path = documents_dir / file.filename
            final_filename = file.filename
            if permanent_path.exists():
                # Add timestamp to avoid overwriting
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = file.filename.rsplit(".", 1)
                final_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
                permanent_path = documents_dir / final_filename

            # Copy to permanent location
            import shutil

            shutil.copy2(temp_file_path, permanent_path)
            logger.info(f"Saved permanent copy to: {permanent_path}")

            # Process document with correct metadata
            # Note: Use permanent path and filename in metadata
            nodes = document_processor.process_document(
                temp_file_path,
                source_type="manual",
                extra_metadata={
                    "uploaded_via": "admin_interface",
                    "uploaded_by": session.email,
                    "filename": final_filename,  # Original filename (or with timestamp if duplicate)
                    "file_path": str(permanent_path),  # Point to permanent location
                },
            )

            # Add to knowledge base
            chunks_added = 0
            if nodes:
                kb_manager.add_nodes(nodes)
                chunks_added = len(nodes)
                logger.info(
                    f"Processed uploaded document: {final_filename} ({chunks_added} chunks)"
                )

                # Generate and save document description
                try:
                    from src.document_processing.description_generator import (
                        description_generator,
                    )

                    # Use relative path from project root
                    relative_path = str(permanent_path)
                    if relative_path.startswith("/app/"):
                        relative_path = relative_path[
                            5:
                        ]  # Remove '/app/' prefix in Docker

                    description_generator.generate_and_save(
                        file_path=relative_path,
                        filename=final_filename,
                        chunks=nodes,
                        file_size=len(content),
                        file_type=file_ext.lstrip("."),
                    )
                    logger.info(f"Generated description for: {final_filename}")
                except Exception as e:
                    # Don't fail the upload if description generation fails
                    logger.error(
                        f"Error generating description for {final_filename}: {e}",
                        exc_info=True,
                    )

            # Log to audit trail
            audit_logger.log_action(
                session.email,
                "document_upload",
                file.filename,
                "success",
                f"chunks:{chunks_added}",
            )

            return {
                "success": True,
                "message": "Document uploaded and processed successfully",
                "filename": file.filename,
                "chunks_added": chunks_added,
            }

        finally:
            # Clean up temp file
            if temp_file_path.exists():
                temp_file_path.unlink()
                logger.debug(f"Cleaned up temp file: {temp_file_path}")

    except HTTPException:
        raise
    except Exception as e:
        # Log failure
        audit_logger.log_action(
            session.email,
            "document_upload",
            file.filename if file else "unknown",
            "error",
            str(e),
        )
        logger.error(f"Error uploading document {file.filename}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error uploading document: {str(e)}"
        )


# Web Crawling Endpoints
@app.post("/api/admin/crawl", response_model=AdminActionResponse)
async def crawl_url(
    request: CrawlRequest,
    session: Session = Depends(require_admin),
):
    """
    Crawl a URL and add content to knowledge base.

    Requires admin privileges.

    Args:
        request: Crawl request with URL and depth
        session: Admin session (injected by dependency)

    Returns:
        AdminActionResponse with crawling details

    Raises:
        HTTPException: If URL is invalid or crawling fails
    """
    try:
        logger.info(
            f"Admin {session.email} initiated crawl: {request.url} (depth={request.crawl_depth})"
        )

        # Process URL with DocumentProcessor
        nodes = document_processor.process_url(
            url=request.url,
            crawl_depth=request.crawl_depth,
            extra_metadata={
                "crawled_via": "admin_interface",
                "crawled_by": session.email,
            },
        )

        # Add to knowledge base
        pages_crawled = 0
        chunks_added = 0
        if nodes:
            kb_manager.add_nodes(nodes)
            chunks_added = len(nodes)

            # Count unique pages (by url_hash)
            unique_urls = set()
            for node in nodes:
                if hasattr(node, "metadata") and "url_hash" in node.metadata:
                    unique_urls.add(node.metadata["url_hash"])
            pages_crawled = len(unique_urls)

            logger.info(
                f"Crawled {pages_crawled} pages from {request.url}: "
                f"{chunks_added} chunks added to KB"
            )

        # Log to audit trail
        audit_logger.log_action(
            session.email,
            "url_crawl",
            request.url,
            "success",
            f"pages:{pages_crawled},chunks:{chunks_added},depth:{request.crawl_depth}",
        )

        message = (
            f"Successfully crawled {pages_crawled} page(s) from {request.url}. "
            f"Added {chunks_added} chunks to knowledge base."
        )

        return AdminActionResponse(
            success=True,
            message=message,
            details={
                "url": request.url,
                "pages_crawled": pages_crawled,
                "chunks_added": chunks_added,
                "crawl_depth": request.crawl_depth,
            },
        )

    except ValueError as e:
        # Invalid URL or crawling error
        audit_logger.log_action(
            session.email, "url_crawl", request.url, "error", str(e)
        )
        logger.error(f"Error crawling {request.url}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        audit_logger.log_action(
            session.email, "url_crawl", request.url, "error", str(e)
        )
        logger.error(f"Error crawling {request.url}: {e}")
        raise HTTPException(status_code=500, detail=f"Error crawling URL: {str(e)}")


@app.get("/api/admin/crawled-urls", response_model=CrawledUrlResponse)
async def list_crawled_urls(
    session: Session = Depends(require_admin),
):
    """
    List all crawled URLs in the knowledge base.

    Requires admin privileges.

    Args:
        session: Admin session (injected by dependency)

    Returns:
        CrawledUrlResponse with list of crawled URLs
    """
    try:
        urls = kb_manager.get_crawled_urls()

        # Format timestamps for display
        from datetime import datetime

        for url in urls:
            if url.get("last_crawled"):
                try:
                    dt = datetime.fromtimestamp(url["last_crawled"])
                    url["last_crawled_formatted"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    url["last_crawled_formatted"] = "Unknown"

        logger.info(f"Admin {session.email} listed crawled URLs ({len(urls)} found)")

        return CrawledUrlResponse(
            urls=urls,
            total_count=len(urls),
        )
    except Exception as e:
        logger.error(f"Error listing crawled URLs: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error listing crawled URLs: {str(e)}"
        )


@app.delete("/api/admin/crawled-urls/all", response_model=AdminActionResponse)
async def delete_all_crawled_urls(
    session: Session = Depends(require_admin),
):
    """
    Delete all crawled URLs from the knowledge base.

    Requires admin privileges.

    Args:
        session: Admin session (injected by dependency)

    Returns:
        AdminActionResponse with deletion summary

    Raises:
        HTTPException: If deletion fails
    """
    try:
        # Get all crawled URLs
        urls = kb_manager.get_crawled_urls()

        if not urls:
            return AdminActionResponse(
                success=True,
                message="No crawled URLs to delete",
                details={
                    "urls_deleted": 0,
                    "chunks_removed": 0,
                },
            )

        # Delete each URL
        total_chunks = 0
        for url_data in urls:
            try:
                chunks = kb_manager.delete_document_by_url_hash(url_data["url_hash"])
                total_chunks += chunks
            except Exception as e:
                logger.warning(f"Error deleting URL {url_data['source_url']}: {e}")
                continue

        # Log to audit trail
        audit_logger.log_action(
            session.email,
            "url_delete_all",
            f"{len(urls)} URLs",
            "success",
            f"urls:{len(urls)},chunks:{total_chunks}",
        )

        message = (
            f"Deleted all {len(urls)} crawled URL(s). "
            f"{total_chunks} chunks removed from KB."
        )

        logger.info(f"Admin {session.email}: {message}")

        return AdminActionResponse(
            success=True,
            message=message,
            details={
                "urls_deleted": len(urls),
                "chunks_removed": total_chunks,
            },
        )

    except Exception as e:
        audit_logger.log_action(
            session.email, "url_delete_all", "all URLs", "error", str(e)
        )
        logger.error(f"Error deleting all crawled URLs: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting all URLs: {str(e)}"
        )


@app.delete("/api/admin/crawled-urls/{url_hash}", response_model=AdminActionResponse)
async def delete_crawled_url(
    url_hash: str,
    session: Session = Depends(require_admin),
):
    """
    Delete a crawled URL from the knowledge base.

    Requires admin privileges.

    Args:
        url_hash: SHA-256 hash of the URL to delete
        session: Admin session (injected by dependency)

    Returns:
        AdminActionResponse with deletion details

    Raises:
        HTTPException: If URL not found or deletion fails
    """
    try:
        # Get URL info before deletion
        url_info = kb_manager.get_document_by_url_hash(url_hash)
        if not url_info:
            raise HTTPException(
                status_code=404, detail=f"Crawled URL not found with hash: {url_hash}"
            )

        source_url = url_info.get("source_url", "Unknown")

        # Delete from KB
        chunks_removed = kb_manager.delete_document_by_url_hash(url_hash)

        # Log to audit trail
        audit_logger.log_action(
            session.email,
            "url_delete",
            source_url,
            "success",
            f"hash:{url_hash},chunks:{chunks_removed}",
        )

        message = (
            f"Deleted crawled URL '{source_url}'. "
            f"{chunks_removed} chunks removed from KB."
        )

        logger.info(f"Admin {session.email}: {message}")

        return AdminActionResponse(
            success=True,
            message=message,
            details={
                "url": source_url,
                "url_hash": url_hash,
                "chunks_removed": chunks_removed,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        audit_logger.log_action(
            session.email, "url_delete", f"hash:{url_hash}", "error", str(e)
        )
        logger.error(f"Error deleting crawled URL {url_hash}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting URL: {str(e)}")


# Backup endpoints
@app.post("/api/admin/backup/create")
async def create_backup(
    background_tasks: BackgroundTasks,
    session: Session = Depends(require_admin),
):
    """
    Create a backup of the data directory.

    Backup is created asynchronously and a download link is emailed to the admin.

    Requires admin privileges.

    Args:
        background_tasks: FastAPI background tasks
        session: Admin session (injected by dependency)

    Returns:
        Success message with backup info

    Raises:
        HTTPException: If backup creation fails
    """
    try:
        # Start backup creation in the background
        async def create_and_notify():
            try:
                # Create the backup
                backup_path = await backup_manager.create_backup(exclude_backups=True)

                # Clean up old backups (keep last 5, delete older than 7 days)
                backup_manager.cleanup_old_backups(max_age_days=7, max_count=5)

                # Generate download link using web base URL
                download_url = (
                    f"{settings.web_base_url}/api/admin/backups/{backup_path.name}"
                )

                # Send email notification to admin
                subject = f"[{settings.instance_name}] Data Backup Ready"
                body = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #333;">Data Backup Complete</h2>

    <p>Your data backup has been created successfully.</p>

    <div style="background-color: #f8f9fa; border-left: 4px solid #007bff; padding: 15px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Backup Details:</strong></p>
        <p style="margin: 5px 0;">Filename: {backup_path.name}</p>
        <p style="margin: 5px 0;">Size: {backup_path.stat().st_size / (1024*1024):.2f} MB</p>
        <p style="margin: 5px 0;">Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>

    <p>
        <a href="{download_url}"
           style="display: inline-block; padding: 12px 24px; background-color: #007bff; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Download Backup
        </a>
    </p>

    <p style="color: #666; font-size: 0.9em;">
        Note: Backup files are automatically cleaned up after 7 days or when more than 5 backups exist.
    </p>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #999; font-size: 0.85em;">
        {settings.instance_name}
        {f"<br>{settings.organization}" if settings.organization else ""}
    </p>
</body>
</html>
                """

                email_sender.send_reply(
                    to_address=session.email,
                    subject=subject,
                    body_text="",  # Empty plain text
                    body_html=body,
                )

                # Log the action
                audit_logger.log_action(
                    session.email,
                    "backup_create",
                    backup_path.name,
                    "success",
                    f"size:{backup_path.stat().st_size}",
                )

                logger.info(f"Admin {session.email} created backup: {backup_path.name}")

            except Exception as e:
                logger.error(f"Error in backup creation task: {e}")
                # Try to send error notification
                try:
                    email_sender.send_reply(
                        to_address=session.email,
                        subject=f"[{settings.instance_name}] Backup Failed",
                        body_text=f"Backup creation failed: {str(e)}",
                        body_html=None,
                    )
                except Exception:
                    pass

        # Add to background tasks
        background_tasks.add_task(create_and_notify)

        return {
            "success": True,
            "message": "Backup creation started. You will receive an email with the download link when complete.",
        }

    except Exception as e:
        logger.error(f"Error starting backup: {e}")
        raise HTTPException(status_code=500, detail=f"Error starting backup: {str(e)}")


@app.get("/api/admin/backups")
async def list_backups(session: Session = Depends(require_admin)):
    """
    List all available backup files.

    Requires admin privileges.

    Args:
        session: Admin session (injected by dependency)

    Returns:
        List of backup files with metadata
    """
    try:
        backups = backup_manager.list_backups()
        return {
            "success": True,
            "backups": backups,
            "count": len(backups),
        }
    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing backups: {str(e)}")


@app.get("/api/admin/backups/{filename}")
async def download_backup(
    filename: str,
    session: Session = Depends(require_admin),
):
    """
    Download a specific backup file.

    Requires admin privileges.

    Args:
        filename: Name of the backup file
        session: Admin session (injected by dependency)

    Returns:
        Backup file download response

    Raises:
        HTTPException: If backup file not found
    """
    try:
        # Get backup path
        backup_path = backup_manager.get_backup_path(filename)

        if not backup_path:
            raise HTTPException(
                status_code=404, detail=f"Backup file not found: {filename}"
            )

        # Log the download
        audit_logger.log_action(
            session.email,
            "backup_download",
            filename,
            "success",
            f"size:{backup_path.stat().st_size}",
        )

        logger.info(f"Admin {session.email} downloaded backup: {filename}")

        return FileResponse(
            backup_path,
            media_type="application/zip",
            filename=filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading backup {filename}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error downloading backup: {str(e)}"
        )


@app.delete("/api/admin/backups/{filename}")
async def delete_backup(
    filename: str,
    session: Session = Depends(require_admin),
):
    """
    Delete a specific backup file.

    Requires admin privileges.

    Args:
        filename: Name of the backup file to delete
        session: Admin session (injected by dependency)

    Returns:
        Success message

    Raises:
        HTTPException: If deletion fails
    """
    try:
        success = backup_manager.delete_backup(filename)

        if not success:
            raise HTTPException(
                status_code=404, detail=f"Backup file not found: {filename}"
            )

        # Log the action
        audit_logger.log_action(
            session.email,
            "backup_delete",
            filename,
            "success",
        )

        logger.info(f"Admin {session.email} deleted backup: {filename}")

        return {
            "success": True,
            "message": f"Backup '{filename}' deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting backup {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting backup: {str(e)}")


# Settings endpoints
@app.get("/api/admin/settings/prompt")
async def get_prompt_settings(session: Session = Depends(require_admin)):
    """
    Get system prompt settings and preview.

    Requires admin privileges.

    Args:
        session: Admin session (injected by dependency)

    Returns:
        System prompt information including base and custom prompts
    """
    try:
        # Get the full system prompt (preview)
        full_prompt = get_system_prompt(
            instance_name=settings.instance_name,
            instance_description=settings.instance_description,
            organization=settings.organization,
            include_tools=True,
        )

        # Get custom prompt content if it exists
        custom_prompt = ""
        custom_prompt_file = settings.rag_custom_prompt_file
        if custom_prompt_file and Path(custom_prompt_file).exists():
            try:
                with open(custom_prompt_file, "r", encoding="utf-8") as f:
                    custom_prompt = f.read()
            except Exception as e:
                logger.error(f"Error reading custom prompt file: {e}")

        # Log the action
        audit_logger.log_action(
            session.email, "settings_view_prompt", "system_prompt", "success"
        )

        return {
            "success": True,
            "full_prompt": full_prompt,
            "custom_prompt": custom_prompt,
            "custom_prompt_file": (
                str(custom_prompt_file) if custom_prompt_file else None
            ),
        }

    except Exception as e:
        logger.error(f"Error getting prompt settings: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting prompt settings: {str(e)}"
        )


@app.post("/api/admin/settings/prompt")
async def update_prompt_settings(
    request: dict,
    session: Session = Depends(require_admin),
):
    """
    Update custom system prompt.

    Requires admin privileges.

    Args:
        request: Dictionary with 'custom_prompt' field
        session: Admin session (injected by dependency)

    Returns:
        Success message

    Raises:
        HTTPException: If update fails
    """
    try:
        custom_prompt = request.get("custom_prompt", "")

        # Ensure the custom prompt file path is set
        if not settings.rag_custom_prompt_file:
            # Set a default path if not configured
            settings.rag_custom_prompt_file = Path("data/config/custom_prompt.txt")

        custom_prompt_file = Path(settings.rag_custom_prompt_file)

        # Ensure directory exists
        custom_prompt_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the custom prompt
        with open(custom_prompt_file, "w", encoding="utf-8") as f:
            f.write(custom_prompt)

        # Log the action
        audit_logger.log_action(
            session.email,
            "settings_update_prompt",
            "system_prompt",
            "success",
            f"length:{len(custom_prompt)}",
        )

        logger.info(
            f"Admin {session.email} updated custom system prompt ({len(custom_prompt)} chars)"
        )

        return {
            "success": True,
            "message": "Custom system prompt updated successfully",
            "custom_prompt_file": str(custom_prompt_file),
        }

    except Exception as e:
        logger.error(f"Error updating prompt settings: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error updating prompt settings: {str(e)}"
        )


@app.get("/api/admin/settings/models")
async def get_model_settings(session: Session = Depends(require_admin)):
    """
    Get information about configured LLM and embedding models.

    Requires admin privileges.

    Args:
        session: Admin session (injected by dependency)

    Returns:
        Model configuration information
    """
    try:
        # Log the action
        audit_logger.log_action(
            session.email, "settings_view_models", "model_info", "success"
        )

        return {
            "success": True,
            "embedding": {
                "model": settings.openai_embedding_model,
                "api_base": settings.openai_api_base,
                "provider": (
                    "Naga.ac"
                    if "naga.ac" in settings.openai_api_base.lower()
                    else "OpenAI"
                ),
            },
            "llm": {
                "model": settings.openrouter_model,
                "api_base": settings.openrouter_api_base,
                "provider": (
                    "Naga.ac"
                    if "naga.ac" in settings.openrouter_api_base.lower()
                    else "OpenRouter"
                ),
            },
            "rag": {
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "top_k_retrieval": settings.top_k_retrieval,
                "similarity_threshold": settings.similarity_threshold,
            },
        }

    except Exception as e:
        logger.error(f"Error getting model settings: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting model settings: {str(e)}"
        )


@app.get("/api/config")
async def get_config():
    """
    Get public instance configuration.

    Returns:
        Instance name, description, and organization
    """
    return {
        "instance_name": settings.instance_name,
        "instance_description": settings.instance_description,
        "organization": settings.organization,
    }


# Usage Analytics Endpoints
@app.get("/api/admin/usage/analytics", response_model=UsageAnalyticsResponse)
async def get_usage_analytics(
    days: Optional[int] = None,
    session: Session = Depends(require_admin),
):
    """
    Get comprehensive usage analytics.

    Requires admin privileges.

    Args:
        days: Number of days to look back (7, 30, 90, or None for all)
        session: Admin session (injected by dependency)

    Returns:
        UsageAnalyticsResponse with comprehensive analytics

    Raises:
        HTTPException: If query fails
    """
    try:
        logger.info(f"Admin {session.email} requested usage analytics (days={days})")

        analytics = conversation_manager.get_usage_analytics(days=days)

        return UsageAnalyticsResponse(**analytics)

    except Exception as e:
        logger.error(f"Error getting usage analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error getting usage analytics: {str(e)}"
        )


@app.get("/api/admin/analytics/optimization")
async def get_optimization_analytics(
    days: Optional[int] = None,
    session: Session = Depends(require_admin),
):
    """
    Get query optimization analytics.

    Requires admin privileges.

    Args:
        days: Number of days to look back (None for all time)
        session: Admin session (injected by dependency)

    Returns:
        Dictionary with optimization statistics

    Raises:
        HTTPException: If query fails
    """
    try:
        logger.info(
            f"Admin {session.email} requested optimization analytics (days={days})"
        )

        analytics = conversation_manager.get_optimization_analytics(days=days)

        # Transform data to match frontend expectations
        return {
            "total_queries": analytics["total_queries"],
            "optimized_count": analytics["optimized_queries"],
            "optimization_rate": analytics["optimization_rate"],
            "avg_query_expansion": (analytics["avg_expansion_ratio"] - 1.0)
            * 100,  # Convert ratio to percentage
            "sample_optimizations": [
                {
                    "original_query": s["original"],
                    "optimized_query": s["optimized"],
                    "timestamp": s.get("timestamp"),
                }
                for s in analytics["sample_optimizations"]
            ],
        }

    except Exception as e:
        logger.error(f"Error getting optimization analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error getting optimization analytics: {str(e)}"
        )


@app.get("/api/admin/analytics/sources")
async def get_source_analytics(
    days: Optional[int] = None,
    session: Session = Depends(require_admin),
):
    """
    Get source document usage analytics.

    Requires admin privileges.

    Args:
        days: Number of days to look back (None for all time)
        session: Admin session (injected by dependency)

    Returns:
        Dictionary with source usage statistics

    Raises:
        HTTPException: If query fails
    """
    try:
        logger.info(f"Admin {session.email} requested source analytics (days={days})")

        analytics = conversation_manager.get_source_analytics(days=days)

        # Transform data to match frontend expectations
        return {
            "total_replies": analytics["total_replies"],
            "replies_with_sources": analytics["total_replies_with_sources"],
            "avg_sources_per_reply": analytics["avg_sources_per_reply"],
            "avg_relevance_score": analytics["avg_relevance_score"],
            "top_sources": analytics["most_cited_documents"],
        }

    except Exception as e:
        logger.error(f"Error getting source analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error getting source analytics: {str(e)}"
        )


@app.get("/api/admin/usage/user/{sender}", response_model=UserQueriesResponse)
async def get_user_queries(
    sender: str,
    days: Optional[int] = None,
    limit: Optional[int] = 100,
    session: Session = Depends(require_admin),
):
    """
    Get detailed query list for a specific user.

    Requires admin privileges.

    Args:
        sender: User identifier (email)
        days: Number of days to look back (None = all)
        limit: Maximum number of queries to return
        session: Admin session (injected by dependency)

    Returns:
        UserQueriesResponse with query details

    Raises:
        HTTPException: If query fails
    """
    try:
        logger.info(
            f"Admin {session.email} requested queries for user {sender} (days={days}, limit={limit})"
        )

        queries = conversation_manager.get_user_queries(
            sender=sender, days=days, limit=limit
        )

        return UserQueriesResponse(
            sender=sender, queries=queries, total_count=len(queries)
        )

    except Exception as e:
        logger.error(f"Error getting user queries: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error getting user queries: {str(e)}"
        )


@app.get("/api/admin/feedback/analytics", response_model=FeedbackAnalyticsResponse)
async def get_feedback_analytics(
    days: Optional[int] = None,
    session: Session = Depends(require_admin),
):
    """
    Get comprehensive feedback analytics.

    Requires admin privileges.

    Args:
        days: Number of days to look back (7, 30, 90, or None for all)
        session: Admin session (injected by dependency)

    Returns:
        FeedbackAnalyticsResponse with overview stats and negative responses

    Raises:
        HTTPException: If query fails
    """
    try:

        from src.email.db_models import ConversationMessage, ResponseFeedback

        logger.info(f"Admin {session.email} requested feedback analytics (days={days})")

        # Determine date range
        start_date = None
        if days:
            start_date = datetime.utcnow() - timedelta(days=days)

        with conversation_manager.db_manager.get_session() as db_session:
            # Base query
            query = db_session.query(ResponseFeedback)

            if start_date:
                query = query.filter(ResponseFeedback.submitted_at >= start_date)

            # Get all feedback
            all_feedback = query.all()

            # Calculate overview stats
            total_feedback = len(all_feedback)
            positive_count = sum(1 for f in all_feedback if f.is_positive)
            negative_count = total_feedback - positive_count
            positive_rate = (
                (positive_count / total_feedback * 100) if total_feedback > 0 else 0
            )

            overview = {
                "total_feedback": total_feedback,
                "positive_count": positive_count,
                "negative_count": negative_count,
                "positive_rate": round(positive_rate, 1),
            }

            # Get negative responses with details
            negative_query = (
                db_session.query(ResponseFeedback, ConversationMessage)
                .join(
                    ConversationMessage,
                    ResponseFeedback.message_id == ConversationMessage.id,
                )
                .filter(ResponseFeedback.is_positive.is_(False))
            )

            if start_date:
                negative_query = negative_query.filter(
                    ResponseFeedback.submitted_at >= start_date
                )

            negative_query = negative_query.order_by(
                ResponseFeedback.submitted_at.desc()
            )

            negative_responses = []
            for feedback, message in negative_query.all():
                negative_responses.append(
                    {
                        "id": feedback.id,
                        "message_id": feedback.message_id,
                        "response_content": (
                            message.content[:200] + "..."
                            if len(message.content) > 200
                            else message.content
                        ),
                        "comment": feedback.comment,
                        "user_email": feedback.user_email,
                        "channel": (
                            feedback.channel.value
                            if hasattr(feedback.channel, "value")
                            else feedback.channel
                        ),
                        "submitted_at": feedback.submitted_at.isoformat(),
                    }
                )

            # Date range
            if start_date:
                date_range = {
                    "start": start_date.date().isoformat(),
                    "end": datetime.utcnow().date().isoformat(),
                }
            else:
                if all_feedback:
                    earliest = min(f.submitted_at for f in all_feedback)
                    date_range = {
                        "start": earliest.date().isoformat(),
                        "end": datetime.utcnow().date().isoformat(),
                    }
                else:
                    date_range = {
                        "start": "N/A",
                        "end": "N/A",
                    }

        return FeedbackAnalyticsResponse(
            date_range=date_range,
            overview=overview,
            negative_responses=negative_responses,
        )

    except Exception as e:
        logger.error(f"Error getting feedback analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error getting feedback analytics: {str(e)}"
        )


@app.post("/api/admin/usage/topics", response_model=TopicClusteringResponse)
async def cluster_query_topics(
    days: Optional[int] = 30,
    session: Session = Depends(require_admin),
):
    """
    Analyze and cluster query topics using LLM.

    Requires admin privileges.

    Args:
        days: Number of days to analyze (default: 30)
        session: Admin session (injected by dependency)

    Returns:
        TopicClusteringResponse with topic analysis

    Raises:
        HTTPException: If analysis fails
    """
    try:
        logger.info(f"Admin {session.email} requested topic clustering (days={days})")

        # Get all queries for the period
        analytics = conversation_manager.get_usage_analytics(days=days)
        total_queries = analytics["overview"]["total_queries"]

        if total_queries == 0:
            return TopicClusteringResponse(
                topics=[],
                total_queries=0,
                clustered_queries=0,
            )

        # Get all query content
        from src.email.db_manager import db_manager
        from src.email.db_models import ConversationMessage

        with db_manager.get_session() as db_session:
            # Calculate start date
            from datetime import timedelta

            start_date = (
                datetime.utcnow() - timedelta(days=days)
                if days
                else datetime(1970, 1, 1)
            )

            queries = (
                db_session.query(ConversationMessage)
                .filter(
                    ConversationMessage.message_type == MessageType.QUERY,
                    ConversationMessage.timestamp >= start_date,
                )
                .all()
            )

            query_texts = [q.content for q in queries]

        # Use LLM to cluster topics
        from src.rag.topic_clustering import cluster_topics

        topics = cluster_topics(query_texts, query_handler.rag_engine)

        return TopicClusteringResponse(
            topics=topics,
            total_queries=total_queries,
            clustered_queries=len(query_texts),
        )

    except Exception as e:
        logger.error(f"Error clustering topics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error clustering topics: {str(e)}"
        )


# Example Questions Endpoints
@app.post("/api/admin/example-questions/generate", response_model=AdminActionResponse)
async def generate_example_questions_endpoint(
    session: Session = Depends(require_admin),
):
    """
    Generate example questions based on the knowledge base.

    Requires admin privileges.

    Args:
        session: Admin session (injected by dependency)

    Returns:
        AdminActionResponse with generation details

    Raises:
        HTTPException: If generation fails
    """
    try:
        from src.rag.example_questions import generate_and_save_example_questions

        logger.info(f"Admin {session.email} requested example question generation")

        # Generate and save questions
        result = generate_and_save_example_questions(
            rag_engine=query_handler.rag_engine, count=15
        )

        # Log to audit trail
        audit_logger.log_action(
            session.email,
            "generate_example_questions",
            "knowledge_base",
            "success",
            f"generated:{result['count']}",
        )

        message = f"Successfully generated {result['count']} example questions"
        logger.info(f"Admin {session.email}: {message}")

        return AdminActionResponse(
            success=True,
            message=message,
            details={
                "count": result["count"],
                "generated_at": result["generated_at"],
            },
        )

    except Exception as e:
        audit_logger.log_action(
            session.email,
            "generate_example_questions",
            "knowledge_base",
            "error",
            str(e),
        )
        logger.error(f"Error generating example questions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error generating example questions: {str(e)}"
        )


@app.get("/api/example-questions")
async def get_example_questions():
    """
    Get example questions for the knowledge base.

    Public endpoint - no authentication required.

    Returns:
        Dictionary with:
            - questions: List of example question strings
            - count: Number of questions
            - generated_at: Timestamp of generation
    """
    try:
        from src.rag.example_questions import load_example_questions

        result = load_example_questions()
        return result

    except FileNotFoundError:
        # Return empty list if not generated yet
        return {
            "questions": [],
            "count": 0,
            "generated_at": None,
        }
    except Exception as e:
        logger.error(f"Error loading example questions: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error loading example questions: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker."""
    return {"status": "healthy", "instance": settings.instance_name}


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info(f"Starting {settings.instance_name} Web API")
    logger.info(f"Instance: {settings.instance_name}")
    logger.info(f"Organization: {settings.organization}")
    logger.info(f"Model: {settings.openrouter_model}")

    # Security warning if OTP is disabled
    if settings.disable_otp_for_dev:
        logger.error("=" * 80)
        logger.error("⚠️  SECURITY WARNING: OTP AUTHENTICATION IS DISABLED!")
        logger.error("⚠️  This is a DEVELOPMENT-ONLY mode with NO email verification.")
        logger.error("⚠️  Anyone with whitelist access can login without verification.")
        logger.error("⚠️  DO NOT USE THIS SETTING IN PRODUCTION!")
        logger.error(
            "⚠️  Set DISABLE_OTP_FOR_DEV=false to enable proper authentication."
        )
        logger.error("=" * 80)


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down Web API")
    # Cleanup all sessions
    for session_id in list(session_manager.sessions.keys()):
        session_manager.delete_session(session_id)
