"""
Admin routes for knowledge base and system management.

Requires admin privileges for all endpoints.
"""

import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.api.models import (
    AdminActionResponse,
    CrawledUrlResponse,
    CrawlRequest,
    DocumentListResponse,
)
from src.api.routes.helpers import resolve_component
from src.rag.rag_engine import get_system_prompt

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/admin", tags=["admin"])


def create_admin_router(
    audit_logger,
    kb_manager,
    document_manager,
    document_processor,
    backup_manager,
    email_sender,
    query_handler,
    settings,
    require_admin,
    require_admin_or_teacher=None,
    component_resolver=None,
    storage_backend=None,
):
    """
    Create admin router with dependency injection.

    Args:
        audit_logger: Audit logger instance
        kb_manager: Knowledge base manager instance
        document_manager: Document manager instance
        document_processor: Document processor instance
        backup_manager: Backup manager instance
        email_sender: Email sender instance
        query_handler: Query handler instance
        settings: Settings instance
        require_admin: Admin authentication dependency function
        component_resolver: ComponentResolver for tenant-aware operations
        storage_backend: StorageBackend for file operations

    Returns:
        Configured APIRouter instance
    """

    def _get_kb(session):
        return resolve_component(component_resolver, session, "kb_manager", kb_manager)

    def _get_dp(session):
        return resolve_component(
            component_resolver, session, "doc_processor", document_processor
        )

    def _get_qh(session):
        return resolve_component(
            component_resolver, session, "query_handler", query_handler
        )

    def _get_desc_gen(session):
        """Get a DescriptionGenerator scoped to the correct tenant DB."""
        from src.document_processing.description_generator import DescriptionGenerator

        if component_resolver:
            components = component_resolver.resolve(session)
            # Reuse the tenant's conversation_manager.db_manager for DB access
            tenant_db = getattr(components.conversation_manager, "db_manager", None)
            if tenant_db:
                return DescriptionGenerator(db_manager=tenant_db)
        return DescriptionGenerator()

    def _get_doc_mgr(session):
        """Get a DocumentManager scoped to the current tenant's KB."""
        from src.api.admin.document_manager import DocumentManager

        return DocumentManager(
            kb_manager=_get_kb(session),
            document_processor=_get_dp(session),
        )

    def _get_questions_path(session):
        """Get tenant-scoped example questions file path (None = ST default)."""
        if component_resolver:
            components = component_resolver.resolve(session)
            ctx = components.context
            # Store in tenant's config directory alongside other tenant config
            tenant_config = ctx.documents_path.parent / "config"
            return tenant_config / "example_questions.json"
        return None

    # Teachers can access document endpoints (with ownership restrictions on delete)
    _require_doc_access = require_admin_or_teacher or require_admin

    # ============================================================================
    # Document Management
    # ============================================================================

    @router.get("/documents", response_model=DocumentListResponse)
    def list_documents(
        session=Depends(_require_doc_access),
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
            doc_mgr = _get_doc_mgr(session)
            documents = doc_mgr.list_documents()
            logger.info(
                f"Admin {session.email} listed documents ({len(documents)} found)"
            )
            return DocumentListResponse(
                documents=documents,
                total_count=len(documents),
            )
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error listing documents: {str(e)}"
            )

    @router.get("/documents/descriptions")
    def get_document_descriptions(
        session=Depends(_require_doc_access),
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
            desc_gen = _get_desc_gen(session)
            descriptions = desc_gen.get_all_descriptions()
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

    @router.delete("/documents/{file_hash}", response_model=AdminActionResponse)
    def delete_document(
        file_hash: str,
        archive: bool = True,
        session=Depends(_require_doc_access),
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
            doc_mgr = _get_doc_mgr(session)

            # Teachers can only delete their own documents
            if not session.is_admin:
                kb = _get_kb(session)
                docs = kb.get_unique_documents()
                doc = next((d for d in docs if d.get("file_hash") == file_hash), None)
                if not doc:
                    raise HTTPException(
                        status_code=404, detail=f"Document not found: {file_hash}"
                    )
                if doc.get("uploaded_by") != session.email:
                    raise HTTPException(
                        status_code=403,
                        detail="You can only delete documents you uploaded.",
                    )

            result = doc_mgr.delete_document(file_hash, archive=archive)

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

    @router.get("/documents/{file_hash}/view")
    def view_document(
        file_hash: str,
        session=Depends(_require_doc_access),
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
            doc_mgr = _get_doc_mgr(session)
            documents = doc_mgr.list_documents()
            doc = next((d for d in documents if d.get("file_hash") == file_hash), None)

            if not doc:
                raise HTTPException(
                    status_code=404, detail=f"Document not found with hash: {file_hash}"
                )

            # Get content from KB
            content = _get_kb(session).get_document_content(file_hash)

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
            raise HTTPException(
                status_code=500, detail=f"Error viewing document: {str(e)}"
            )

    @router.get("/documents/{file_hash}/download")
    def download_document(
        file_hash: str,
        session=Depends(_require_doc_access),
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
            doc_mgr = _get_doc_mgr(session)
            documents = doc_mgr.list_documents()
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
            file_path = doc_mgr.documents_path / filename

            if not file_path.exists():
                raise HTTPException(
                    status_code=404, detail=f"File not found: {filename}"
                )

            # Log the download action
            audit_logger.log_action(
                session.email,
                "document_download",
                filename,
                "success",
                f"hash:{file_hash}",
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

    @router.post("/documents/upload")
    async def upload_document(
        file: UploadFile = File(...),
        session=Depends(_require_doc_access),
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
            from src.document_processing.document_processor import SUPPORTED_EXTENSIONS

            file_ext = Path(file.filename).suffix.lower()

            if file_ext not in SUPPORTED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {file_ext}. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
                )

            # Check billing storage limit before accepting upload
            if component_resolver and session.tenant_slug:
                _check_billing_storage_limit(session, component_resolver, file.size)

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

                # Save permanent copy to kb/documents/
                # In MT mode with storage_backend, resolve tenant-specific path
                if storage_backend and component_resolver and session.tenant_slug:
                    components = component_resolver.resolve(session)
                    documents_dir = components.context.kb_documents_path
                else:
                    documents_dir = settings.kb_documents_path

                final_filename = file.filename

                if storage_backend and session.tenant_slug:
                    # MT mode: archive via storage backend
                    storage_backend.put(
                        session.tenant_slug,
                        f"kb/documents/{final_filename}",
                        content,
                    )
                    permanent_path = documents_dir / final_filename
                    logger.info(
                        f"Archived upload to storage backend "
                        f"({session.tenant_slug}/kb/documents/{final_filename})"
                    )
                else:
                    # ST mode: local filesystem with collision handling
                    documents_dir.mkdir(parents=True, exist_ok=True)
                    permanent_path = documents_dir / file.filename
                    if permanent_path.exists():
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        name_parts = file.filename.rsplit(".", 1)
                        final_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
                        permanent_path = documents_dir / final_filename
                    shutil.copy2(temp_file_path, permanent_path)
                    logger.info(f"Saved permanent copy to: {permanent_path}")

                # Process document with correct metadata
                # Note: Use permanent path and filename in metadata
                nodes = _get_dp(session).process_document(
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
                    _get_kb(session).add_nodes(nodes)
                    chunks_added = len(nodes)
                    logger.info(
                        f"Processed uploaded document: {final_filename} ({chunks_added} chunks)"
                    )

                    # Generate and save document description
                    try:
                        desc_gen = _get_desc_gen(session)

                        # Use relative path from project root
                        relative_path = str(permanent_path)
                        if relative_path.startswith("/app/"):
                            relative_path = relative_path[
                                5:
                            ]  # Remove '/app/' prefix in Docker

                        desc_gen.generate_and_save(
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

    # ============================================================================
    # Web Crawling Management
    # ============================================================================

    @router.post("/crawl", response_model=AdminActionResponse)
    def crawl_url(
        request: CrawlRequest,
        session=Depends(require_admin),
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
        # Check storage limit before crawling (MT mode)
        if component_resolver and session.tenant_slug:
            _check_billing_storage_limit(session, component_resolver, 0)

        try:
            logger.info(
                f"Admin {session.email} initiated crawl: {request.url} (depth={request.crawl_depth})"
            )

            # Process URL with DocumentProcessor
            nodes = _get_dp(session).process_url(
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
                _get_kb(session).add_nodes(nodes)
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

    @router.get("/crawled-urls", response_model=CrawledUrlResponse)
    def list_crawled_urls(
        session=Depends(require_admin),
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
            urls = _get_kb(session).get_crawled_urls()

            # Format timestamps for display
            for url in urls:
                if url.get("last_crawled"):
                    try:
                        dt = datetime.fromtimestamp(url["last_crawled"])
                        url["last_crawled_formatted"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        url["last_crawled_formatted"] = "Unknown"

            logger.info(
                f"Admin {session.email} listed crawled URLs ({len(urls)} found)"
            )

            return CrawledUrlResponse(
                urls=urls,
                total_count=len(urls),
            )
        except Exception as e:
            logger.error(f"Error listing crawled URLs: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error listing crawled URLs: {str(e)}"
            )

    @router.delete("/crawled-urls/all", response_model=AdminActionResponse)
    def delete_all_crawled_urls(
        session=Depends(require_admin),
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
            urls = _get_kb(session).get_crawled_urls()

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
                    chunks = _get_kb(session).delete_document_by_url_hash(
                        url_data["url_hash"]
                    )
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

    @router.delete("/crawled-urls/{url_hash}", response_model=AdminActionResponse)
    def delete_crawled_url(
        url_hash: str,
        session=Depends(require_admin),
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
            url_info = _get_kb(session).get_document_by_url_hash(url_hash)
            if not url_info:
                raise HTTPException(
                    status_code=404,
                    detail=f"Crawled URL not found with hash: {url_hash}",
                )

            source_url = url_info.get("source_url", "Unknown")

            # Delete from KB
            chunks_removed = _get_kb(session).delete_document_by_url_hash(url_hash)

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

    # ============================================================================
    # Backup Management
    # ============================================================================

    @router.post("/backup/create")
    def create_backup(
        background_tasks: BackgroundTasks,
        session=Depends(require_admin),
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
                    backup_path = await backup_manager.create_backup(
                        exclude_backups=True
                    )

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
    <h2 style="color: #2E2E2E;">Data Backup Complete</h2>

    <p>Your data backup has been created successfully.</p>

    <div style="background-color: #F7F2EA; border-left: 4px solid #7A5C3E; padding: 15px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Backup Details:</strong></p>
        <p style="margin: 5px 0;">Filename: {backup_path.name}</p>
        <p style="margin: 5px 0;">Size: {backup_path.stat().st_size / (1024*1024):.2f} MB</p>
        <p style="margin: 5px 0;">Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>

    <p>
        <a href="{download_url}"
           style="display: inline-block; padding: 12px 24px; background-color: #7A5C3E; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Download Backup
        </a>
    </p>

    <p style="color: #8C8279; font-size: 0.9em;">
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

                    logger.info(
                        f"Admin {session.email} created backup: {backup_path.name}"
                    )

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
            raise HTTPException(
                status_code=500, detail=f"Error starting backup: {str(e)}"
            )

    @router.get("/backups")
    def list_backups(session=Depends(require_admin)):
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
            raise HTTPException(
                status_code=500, detail=f"Error listing backups: {str(e)}"
            )

    @router.get("/backups/{filename}")
    def download_backup(
        filename: str,
        session=Depends(require_admin),
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

    @router.delete("/backups/{filename}")
    def delete_backup(
        filename: str,
        session=Depends(require_admin),
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
            raise HTTPException(
                status_code=500, detail=f"Error deleting backup: {str(e)}"
            )

    # ============================================================================
    # Backup Restore
    # ============================================================================

    @router.post("/backup/validate")
    async def validate_backup_upload(
        file: UploadFile = File(...),
        session=Depends(require_admin),
    ):
        """
        Validate an uploaded backup ZIP without restoring.

        Args:
            file: Uploaded ZIP file.
            session: Admin session (injected by dependency).

        Returns:
            Validation report.
        """
        temp_path = None
        try:
            # Save upload to temp file
            temp_id = uuid.uuid4().hex[:8]
            temp_path = Path(f"/tmp/backup_validate_{temp_id}.zip")
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            report = backup_manager.validate_backup(temp_path)
            return {"success": True, **report}

        except Exception as e:
            logger.error(f"Error validating backup: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error validating backup: {str(e)}"
            )
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    @router.post("/backup/restore")
    def restore_backup_upload(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        session=Depends(require_admin),
    ):
        """
        Upload a backup ZIP and restore from it.

        Restore runs in background. Admin receives email on completion/failure.

        Args:
            file: Uploaded ZIP file.
            background_tasks: FastAPI background tasks.
            session: Admin session (injected by dependency).

        Returns:
            Acknowledgement message.
        """
        try:
            # Save upload to a persistent temp file (background task needs it)
            temp_id = uuid.uuid4().hex[:8]
            temp_path = Path(f"/tmp/backup_restore_{temp_id}.zip")
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            async def restore_and_notify():
                try:
                    result = await backup_manager.restore_backup(
                        temp_path, create_pre_restore=True
                    )

                    if result["success"]:
                        subject = f"[{settings.instance_name}] Backup Restore Complete"
                        body = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #2E2E2E;">Backup Restore Complete</h2>
    <p>Your data has been restored successfully.</p>
    <div style="background-color: #F7F2EA; border-left: 4px solid #5B8C7A; padding: 15px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Restore Details:</strong></p>
        <p style="margin: 5px 0;">Files Restored: {result['files_restored']}</p>
        <p style="margin: 5px 0;">Safety Backup: {result['pre_restore_backup'] or 'None'}</p>
        <p style="margin: 5px 0;">Completed: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
    <p style="color: #8C8279; font-size: 0.9em;">
        A safety backup was created before the restore. You can find it in the backups list.
    </p>
</body>
</html>
                        """
                    else:
                        subject = f"[{settings.instance_name}] Backup Restore Failed"
                        errors_html = "".join(f"<li>{e}</li>" for e in result["errors"])
                        body = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #A3423A;">Backup Restore Failed</h2>
    <p>The restore operation failed. Your data has been rolled back to its previous state.</p>
    <div style="background-color: #FFF0F0; border-left: 4px solid #A3423A; padding: 15px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Errors:</strong></p>
        <ul>{errors_html}</ul>
    </div>
</body>
</html>
                        """

                    email_sender.send_reply(
                        to_address=session.email,
                        subject=subject,
                        body_text="",
                        body_html=body,
                    )

                    audit_logger.log_action(
                        session.email,
                        "backup_restore_upload",
                        file.filename or "uploaded.zip",
                        "success" if result["success"] else "failed",
                        f"files:{result['files_restored']}",
                    )

                except Exception as e:
                    logger.error(f"Error in backup restore task: {e}")
                    try:
                        email_sender.send_reply(
                            to_address=session.email,
                            subject=f"[{settings.instance_name}] Backup Restore Failed",
                            body_text=f"Restore failed: {str(e)}",
                            body_html=None,
                        )
                    except Exception:
                        pass
                finally:
                    if temp_path.exists():
                        temp_path.unlink()

            background_tasks.add_task(restore_and_notify)

            return {
                "success": True,
                "message": "Restore started. You will receive an email when complete.",
            }

        except Exception as e:
            logger.error(f"Error starting restore: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error starting restore: {str(e)}"
            )

    @router.post("/backups/{filename}/restore")
    def restore_existing_backup(
        filename: str,
        background_tasks: BackgroundTasks,
        session=Depends(require_admin),
    ):
        """
        Restore from an existing backup file.

        Args:
            filename: Name of the backup file to restore.
            background_tasks: FastAPI background tasks.
            session: Admin session (injected by dependency).

        Returns:
            Acknowledgement message.
        """
        try:
            backup_path = backup_manager.get_backup_path(filename)
            if not backup_path:
                raise HTTPException(
                    status_code=404, detail=f"Backup file not found: {filename}"
                )

            async def restore_and_notify():
                try:
                    result = await backup_manager.restore_backup(
                        backup_path, create_pre_restore=True
                    )

                    if result["success"]:
                        subject = f"[{settings.instance_name}] Backup Restore Complete"
                        body = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #2E2E2E;">Backup Restore Complete</h2>
    <p>Data restored from <strong>{filename}</strong>.</p>
    <div style="background-color: #F7F2EA; border-left: 4px solid #5B8C7A; padding: 15px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Restore Details:</strong></p>
        <p style="margin: 5px 0;">Files Restored: {result['files_restored']}</p>
        <p style="margin: 5px 0;">Safety Backup: {result['pre_restore_backup'] or 'None'}</p>
        <p style="margin: 5px 0;">Completed: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
</body>
</html>
                        """
                    else:
                        errors_html = "".join(f"<li>{e}</li>" for e in result["errors"])
                        subject = f"[{settings.instance_name}] Backup Restore Failed"
                        body = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #A3423A;">Backup Restore Failed</h2>
    <p>Failed to restore from <strong>{filename}</strong>. Data has been rolled back.</p>
    <div style="background-color: #FFF0F0; border-left: 4px solid #A3423A; padding: 15px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Errors:</strong></p>
        <ul>{errors_html}</ul>
    </div>
</body>
</html>
                        """

                    email_sender.send_reply(
                        to_address=session.email,
                        subject=subject,
                        body_text="",
                        body_html=body,
                    )

                    audit_logger.log_action(
                        session.email,
                        "backup_restore",
                        filename,
                        "success" if result["success"] else "failed",
                        f"files:{result['files_restored']}",
                    )

                except Exception as e:
                    logger.error(f"Error in backup restore task: {e}")
                    try:
                        email_sender.send_reply(
                            to_address=session.email,
                            subject=f"[{settings.instance_name}] Backup Restore Failed",
                            body_text=f"Restore failed: {str(e)}",
                            body_html=None,
                        )
                    except Exception:
                        pass

            background_tasks.add_task(restore_and_notify)

            return {
                "success": True,
                "message": f"Restoring from '{filename}'. You will receive an email when complete.",
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error starting restore from {filename}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error starting restore: {str(e)}"
            )

    # ============================================================================
    # Settings Management
    # ============================================================================

    @router.get("/settings/prompt")
    def get_prompt_settings(session=Depends(require_admin)):
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

    @router.post("/settings/prompt")
    def update_prompt_settings(
        request: dict,
        session=Depends(require_admin),
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

    @router.get("/settings/models")
    def get_model_settings(session=Depends(require_admin)):
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
                    "fallback_model": settings.openrouter_fallback_model,
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
                "reranking": {
                    "enabled": settings.reranking_enabled,
                    "active": settings.reranking_enabled
                    and bool(settings.cohere_api_key),
                    "model": settings.reranking_model,
                    "top_n": settings.reranking_top_n or settings.top_k_retrieval,
                    "provider": "Cohere",
                },
            }

        except Exception as e:
            logger.error(f"Error getting model settings: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error getting model settings: {str(e)}"
            )

    # ============================================================================
    # Example Questions Management
    # ============================================================================

    @router.post("/example-questions/generate", response_model=AdminActionResponse)
    def generate_example_questions_endpoint(
        session=Depends(require_admin),
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

            # Generate and save questions (tenant-scoped path in MT mode)
            result = generate_and_save_example_questions(
                rag_engine=_get_qh(session).rag_engine,
                count=15,
                file_path=_get_questions_path(session),
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

    return router


def _check_billing_storage_limit(session, component_resolver, file_size):
    """Check if uploading a file would exceed the tenant's storage limit.

    Raises HTTPException 429 if the limit is exceeded.
    """
    try:
        from src.billing.plans import check_storage_limit
        from src.billing.router import _get_storage_used_mb
        from src.platform.models import Tenant

        db_manager = component_resolver.component_factory.db_manager

        with db_manager.get_platform_session() as db:
            tenant = db.query(Tenant).filter(Tenant.slug == session.tenant_slug).first()
            if not tenant:
                return

            storage_used_mb = _get_storage_used_mb(db_manager, tenant)
            new_file_mb = (file_size or 0) / (1024 * 1024)
            check_storage_limit(
                tenant.plan,
                tenant.subscription_status,
                storage_used_mb,
                new_file_mb,
            )
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Storage billing check failed (allowing upload): %s", e)
