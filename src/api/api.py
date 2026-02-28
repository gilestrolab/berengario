"""
FastAPI web interface for RAG query testing.

Provides a REST API and web UI for real-time RAG queries with conversation threading.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
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

# Import models still used in main api.py
from src.api.models import (
    StatsResponse,
)
from src.api.routes.admin import create_admin_router
from src.api.routes.analytics import create_analytics_router
from src.api.routes.auth import create_auth_router
from src.api.routes.conversations import create_conversations_router
from src.api.routes.feedback import create_feedback_router
from src.api.routes.query import create_query_router
from src.api.routes.team import create_team_router
from src.config import settings
from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.email.conversation_manager import conversation_manager
from src.email.email_sender import EmailSender
from src.email.whitelist_validator import WhitelistValidator
from src.rag.query_handler import QueryHandler

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

# Multi-tenant initialization
platform_db_manager = None
component_resolver = None

if settings.multi_tenant:
    from src.platform.component_factory import TenantComponentFactory
    from src.platform.component_resolver import ComponentResolver
    from src.platform.db_manager import TenantDBManager
    from src.platform.storage import create_storage_backend

    logger.info("Multi-tenant mode enabled. Initializing platform components...")
    platform_db_manager = TenantDBManager()
    platform_db_manager.init_platform_db()
    storage_backend = create_storage_backend()
    component_factory = TenantComponentFactory(
        storage_backend=storage_backend,
        db_manager=platform_db_manager,
    )
    component_resolver = ComponentResolver(
        multi_tenant=True,
        component_factory=component_factory,
    )
    logger.info("Multi-tenant platform components initialized")

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
    platform_db_manager=platform_db_manager,
)

# Include auth router
app.include_router(auth_router)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Setup templates (using same directory as static for HTML templates)
templates = Jinja2Templates(directory=str(static_dir))


# Version information
def get_version() -> str:
    """Get version string combining package version, git branch, and commit."""
    import os
    import subprocess

    base_version = "0.1.0"  # From pyproject.toml

    # Try environment variables first (set by docker-compose)
    git_branch = os.getenv("GIT_BRANCH")
    git_commit = os.getenv("GIT_COMMIT")

    if (
        git_branch
        and git_commit
        and git_branch != "unknown"
        and git_commit != "unknown"
    ):
        return f"{base_version} ({git_branch}@{git_commit})"

    # Fall back to git commands if running locally
    try:
        repo_path = Path(__file__).parent.parent.parent

        # Get git branch
        git_branch = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=repo_path,
            )
            .decode()
            .strip()
        )

        # Get git commit hash
        git_hash = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=repo_path,
            )
            .decode()
            .strip()
        )

        return f"{base_version} ({git_branch}@{git_hash})"
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
    component_resolver=component_resolver,
)

conversations_router = create_conversations_router(
    conversation_manager=conversation_manager,
    session_manager=session_manager,
    require_auth=require_auth,
    component_resolver=component_resolver,
)

query_router = create_query_router(
    query_handler=query_handler,
    conversation_manager=conversation_manager,
    session_manager=session_manager,
    settings=settings,
    require_auth=require_auth,
    set_session_cookie=set_session_cookie,
    cleanup_old_attachments=cleanup_old_attachments,
    component_resolver=component_resolver,
)

admin_router = create_admin_router(
    whitelist_manager=whitelist_manager,
    whitelist_validators=whitelist_validators,
    audit_logger=audit_logger,
    kb_manager=kb_manager,
    document_manager=document_manager,
    document_processor=document_processor,
    backup_manager=backup_manager,
    email_sender=email_sender,
    query_handler=query_handler,
    settings=settings,
    require_admin=require_admin,
    component_resolver=component_resolver,
)

analytics_router = create_analytics_router(
    conversation_manager=conversation_manager,
    query_handler=query_handler,
    require_admin=require_admin,
    component_resolver=component_resolver,
)

# Include routers
app.include_router(feedback_router)
app.include_router(conversations_router)
app.include_router(query_router)
app.include_router(admin_router)
app.include_router(analytics_router)

# Multi-tenant routers (MT mode only)
if settings.multi_tenant and platform_db_manager:
    from src.api.routes.onboarding import create_onboarding_router
    from src.api.routes.tenant_admin import create_tenant_admin_router

    team_router = create_team_router(
        platform_db_manager=platform_db_manager,
        require_admin=require_admin,
    )
    app.include_router(team_router)

    onboarding_router = create_onboarding_router(
        platform_db_manager=platform_db_manager,
        session_manager=session_manager,
        get_session_id=get_session_id,
        set_session_cookie=set_session_cookie,
        settings=settings,
    )
    app.include_router(onboarding_router)

    tenant_admin_router = create_tenant_admin_router(
        platform_db_manager=platform_db_manager,
        require_admin=require_admin,
        session_manager=session_manager,
        get_session_id=get_session_id,
        settings=settings,
    )
    app.include_router(tenant_admin_router)


# API Endpoints
# Note: Authentication endpoints moved to routes/auth.py
# Note: Feedback endpoints moved to routes/feedback.py
# Note: Conversation endpoints moved to routes/conversations.py
# Note: Query endpoints moved to routes/query.py
# Note: Admin endpoints moved to routes/admin.py
# Note: Analytics endpoints moved to routes/analytics.py


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

    # MT onboarding: verified email but no tenant yet → redirect to onboarding
    if settings.multi_tenant and session.onboarding_verified and not session.tenant_id:
        return RedirectResponse(url="/static/onboarding.html", status_code=303)

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
        "multi_tenant": settings.multi_tenant,
    }


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
