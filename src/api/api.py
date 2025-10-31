"""
FastAPI web interface for RAG query testing.

Provides a REST API and web UI for real-time RAG queries with conversation threading.
"""

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from src.config import settings
from src.rag.query_handler import QueryHandler

logger = logging.getLogger(__name__)


# Request/Response Models
class QueryRequest(BaseModel):
    """Request model for query endpoint."""

    query: str
    context: Optional[Dict] = None


class QueryResponse(BaseModel):
    """Response model for query endpoint."""

    success: bool
    response: Optional[str] = None
    sources: Optional[List[Dict]] = None
    attachments: Optional[List[Dict]] = None
    error: Optional[str] = None
    timestamp: str
    session_id: str


class HistoryResponse(BaseModel):
    """Response model for history endpoint."""

    session_id: str
    messages: List[Dict]
    created_at: str
    last_activity: str


class StatsResponse(BaseModel):
    """Response model for KB stats endpoint."""

    total_chunks: int
    unique_documents: int
    documents: List[str]


# Session Management
@dataclass
class Session:
    """
    User session with conversation history.

    Attributes:
        session_id: Unique session identifier
        messages: List of conversation messages
        attachments: List of attachments for this session
        created_at: Session creation timestamp
        last_activity: Last activity timestamp
    """

    session_id: str
    messages: List[Dict] = field(default_factory=list)
    attachments: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str, sources: Optional[List] = None, attachments: Optional[List] = None):
        """
        Add a message to conversation history.

        Args:
            role: Message role (user or assistant)
            content: Message content
            sources: Optional list of sources
            attachments: Optional list of attachments
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if sources:
            message["sources"] = sources
        if attachments:
            message["attachments"] = attachments
            # Track attachments for cleanup
            self.attachments.extend(attachments)

        self.messages.append(message)
        self.last_activity = datetime.now()


class SessionManager:
    """
    Manages user sessions with in-memory storage.

    Attributes:
        sessions: Dictionary of active sessions
        session_timeout: Inactivity timeout in seconds
    """

    def __init__(self, session_timeout: int = 3600):
        """
        Initialize session manager.

        Args:
            session_timeout: Session inactivity timeout in seconds (default 1 hour)
        """
        self.sessions: Dict[str, Session] = {}
        self.session_timeout = session_timeout
        logger.info(f"SessionManager initialized with {session_timeout}s timeout")

    def get_or_create_session(self, session_id: Optional[str] = None) -> Session:
        """
        Get existing session or create new one.

        Args:
            session_id: Optional session ID to retrieve

        Returns:
            Session object
        """
        # Create new session if no ID provided
        if not session_id:
            session_id = str(uuid.uuid4())
            session = Session(session_id=session_id)
            self.sessions[session_id] = session
            logger.info(f"Created new session: {session_id}")
            return session

        # Return existing session if found
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.last_activity = datetime.now()
            return session

        # Create new session with provided ID
        session = Session(session_id=session_id)
        self.sessions[session_id] = session
        logger.info(f"Created session with provided ID: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session object or None if not found
        """
        return self.sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """
        Delete session and cleanup attachments.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted, False if not found
        """
        if session_id not in self.sessions:
            return False

        session = self.sessions[session_id]

        # Cleanup session attachments
        session_dir = settings.email_temp_dir / f"web_{session_id}"
        if session_dir.exists():
            try:
                import shutil
                shutil.rmtree(session_dir)
                logger.info(f"Cleaned up attachments for session {session_id}")
            except Exception as e:
                logger.error(f"Error cleaning up session attachments: {e}")

        del self.sessions[session_id]
        logger.info(f"Deleted session: {session_id}")
        return True

    def cleanup_inactive_sessions(self):
        """Remove sessions inactive beyond timeout."""
        now = datetime.now()
        to_delete = []

        for session_id, session in self.sessions.items():
            if (now - session.last_activity).total_seconds() > self.session_timeout:
                to_delete.append(session_id)

        for session_id in to_delete:
            self.delete_session(session_id)

        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} inactive sessions")


# Initialize components
app = FastAPI(
    title=f"{settings.instance_name} API",
    description=settings.instance_description,
    version="1.0.0",
)

session_manager = SessionManager(session_timeout=3600)  # 1 hour timeout
query_handler = QueryHandler()

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Helper functions
def get_session_id(request: Request) -> Optional[str]:
    """Extract session ID from cookie."""
    return request.cookies.get("session_id")


def set_session_cookie(response: Response, session_id: str):
    """Set session ID cookie."""
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=3600 * 24 * 7,  # 7 days
        httponly=True,
        samesite="lax",
    )


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


# API Endpoints
@app.get("/")
async def root():
    """Serve main web interface."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": f"Welcome to {settings.instance_name} API", "docs": "/docs"}


@app.post("/api/query", response_model=QueryResponse)
async def query(
    query_request: QueryRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
):
    """
    Process a RAG query and return response.

    Args:
        query_request: Query request with text and optional context
        request: FastAPI request object
        response: FastAPI response object
        background_tasks: Background task manager

    Returns:
        QueryResponse with answer, sources, and attachments
    """
    # Get or create session
    session_id = get_session_id(request)
    session = session_manager.get_or_create_session(session_id)
    set_session_cookie(response, session.session_id)

    # Add user message to history
    session.add_message("user", query_request.query)

    try:
        # Process query through RAG engine
        result = query_handler.process_query(
            query_text=query_request.query,
            user_email=f"web_user_{session.session_id[:8]}",
            context=query_request.context,
        )

        if not result["success"]:
            session.add_message("assistant", f"Error: {result.get('error', 'Unknown error')}")
            return QueryResponse(
                success=False,
                error=result.get("error", "Unknown error"),
                timestamp=result["timestamp"],
                session_id=session.session_id,
            )

        # Process attachments - save to session directory and generate URLs
        attachment_urls = []
        if result.get("attachments"):
            session_dir = settings.email_temp_dir / f"web_{session.session_id}"
            session_dir.mkdir(parents=True, exist_ok=True)

            for attachment in result["attachments"]:
                filename = attachment.get("filename", "attachment")
                content = attachment.get("content")

                if isinstance(content, str):
                    content = content.encode("utf-8")

                filepath = session_dir / filename
                with open(filepath, "wb") as f:
                    f.write(content)

                attachment_url = {
                    "filename": filename,
                    "url": f"/api/attachments/{session.session_id}/{filename}",
                    "content_type": attachment.get("content_type", "application/octet-stream"),
                }
                attachment_urls.append(attachment_url)

        # Add assistant response to history
        session.add_message(
            "assistant",
            result["response"],
            sources=result["sources"],
            attachments=attachment_urls,
        )

        # Schedule cleanup
        background_tasks.add_task(session_manager.cleanup_inactive_sessions)
        background_tasks.add_task(cleanup_old_attachments)

        return QueryResponse(
            success=True,
            response=result["response"],
            sources=result["sources"],
            attachments=attachment_urls,
            timestamp=result["timestamp"],
            session_id=session.session_id,
        )

    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        error_msg = str(e)
        session.add_message("assistant", f"Error: {error_msg}")

        return QueryResponse(
            success=False,
            error=error_msg,
            timestamp=datetime.now().isoformat(),
            session_id=session.session_id,
        )


@app.get("/api/history", response_model=HistoryResponse)
async def get_history(request: Request, response: Response):
    """
    Get conversation history for session.

    Args:
        request: FastAPI request object
        response: FastAPI response object

    Returns:
        HistoryResponse with conversation messages
    """
    session_id = get_session_id(request)
    if not session_id:
        # Create new session
        session = session_manager.get_or_create_session()
        set_session_cookie(response, session.session_id)
    else:
        session = session_manager.get_session(session_id)
        if not session:
            # Session expired, create new one
            session = session_manager.get_or_create_session()
            set_session_cookie(response, session.session_id)

    return HistoryResponse(
        session_id=session.session_id,
        messages=session.messages,
        created_at=session.created_at.isoformat(),
        last_activity=session.last_activity.isoformat(),
    )


@app.delete("/api/session")
async def clear_session(request: Request, response: Response):
    """
    Clear session history and delete attachments.

    Args:
        request: FastAPI request object
        response: FastAPI response object

    Returns:
        Success message
    """
    session_id = get_session_id(request)
    if session_id and session_manager.delete_session(session_id):
        # Clear cookie
        response.delete_cookie("session_id")
        return {"success": True, "message": "Session cleared"}

    return {"success": False, "message": "No active session"}


@app.get("/api/attachments/{session_id}/{filename}")
async def download_attachment(session_id: str, filename: str):
    """
    Download attachment file.

    Args:
        session_id: Session ID
        filename: Attachment filename

    Returns:
        File download response

    Raises:
        HTTPException: If file not found
    """
    filepath = settings.email_temp_dir / f"web_{session_id}" / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Determine content type
    content_type = "application/octet-stream"
    if filename.endswith(".ics"):
        content_type = "text/calendar"
    elif filename.endswith(".csv"):
        content_type = "text/csv"
    elif filename.endswith(".json"):
        content_type = "application/json"

    return FileResponse(
        filepath,
        media_type=content_type,
        filename=filename,
    )


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get knowledge base statistics.

    Returns:
        StatsResponse with KB stats
    """
    try:
        stats = query_handler.get_stats()
        return StatsResponse(
            total_chunks=stats.get("total_chunks", 0),
            unique_documents=stats.get("unique_documents", 0),
            documents=stats.get("documents", []),
        )
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return StatsResponse(total_chunks=0, unique_documents=0, documents=[])


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


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down Web API")
    # Cleanup all sessions
    for session_id in list(session_manager.sessions.keys()):
        session_manager.delete_session(session_id)
