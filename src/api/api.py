"""
FastAPI web interface for RAG query testing.

Provides a REST API and web UI for real-time RAG queries with conversation threading.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends,
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

# Import models still used in main api.py (analytics models)
from src.api.models import (
    FeedbackAnalyticsResponse,
    StatsResponse,
    TopicClusteringResponse,
    UsageAnalyticsResponse,
    UserQueriesResponse,
)
from src.api.routes.admin import create_admin_router
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
)

# Include routers
app.include_router(feedback_router)
app.include_router(conversations_router)
app.include_router(query_router)
app.include_router(admin_router)


# API Endpoints
# Note: Authentication endpoints moved to routes/auth.py
# Note: Feedback endpoints moved to routes/feedback.py
# Note: Conversation endpoints moved to routes/conversations.py
# Note: Query endpoints moved to routes/query.py
# Note: Admin endpoints moved to routes/admin.py


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


# Analytics Endpoints (Note: Admin endpoints moved to routes/admin.py)


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
