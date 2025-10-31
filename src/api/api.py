"""
FastAPI web interface for RAG query testing.

Provides a REST API and web UI for real-time RAG queries with conversation threading.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr

from src.config import settings
from src.rag.query_handler import QueryHandler
from src.email.email_sender import EmailSender
from src.email.whitelist_validator import WhitelistValidator
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.document_processing.document_processor import DocumentProcessor
from src.api.admin.whitelist_manager import WhitelistManager
from src.api.admin.document_manager import DocumentManager
from src.api.admin.audit_logger import AdminAuditLogger

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


# Authentication Models
class OTPRequest(BaseModel):
    """Request model for OTP generation."""

    email: EmailStr


class OTPVerifyRequest(BaseModel):
    """Request model for OTP verification."""

    email: EmailStr
    otp_code: str


class AuthResponse(BaseModel):
    """Response model for authentication operations."""

    success: bool
    message: str
    email: Optional[str] = None


class AuthStatusResponse(BaseModel):
    """Response model for authentication status."""

    authenticated: bool
    email: Optional[str] = None
    session_id: Optional[str] = None
    is_admin: bool = False


# Admin Models
class WhitelistEntryRequest(BaseModel):
    """Request model for whitelist entry operations."""

    entry: str


class WhitelistResponse(BaseModel):
    """Response model for whitelist data."""

    entries: List[str]
    whitelist_type: str


class AdminActionResponse(BaseModel):
    """Response model for admin actions."""

    success: bool
    message: str
    details: Optional[Dict] = None


class DocumentListResponse(BaseModel):
    """Response model for document list."""

    documents: List[Dict]
    total_count: int


class DocumentDeleteRequest(BaseModel):
    """Request model for document deletion."""

    file_hash: str
    archive: bool = True


# OTP Management
@dataclass
class OTPEntry:
    """
    OTP entry with expiration and attempt tracking.

    Attributes:
        code: 6-digit OTP code
        email: Email address
        created_at: Creation timestamp
        expires_at: Expiration timestamp
        attempts: Number of verification attempts
        max_attempts: Maximum allowed attempts
    """

    code: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(minutes=5))
    attempts: int = 0
    max_attempts: int = 5

    def is_expired(self) -> bool:
        """Check if OTP has expired."""
        return datetime.now() > self.expires_at

    def is_locked(self) -> bool:
        """Check if maximum attempts reached."""
        return self.attempts >= self.max_attempts

    def increment_attempts(self) -> None:
        """Increment verification attempts."""
        self.attempts += 1


class OTPManager:
    """
    Manages OTP generation, storage, and verification.

    Attributes:
        otps: Dictionary of email -> OTPEntry
    """

    def __init__(self):
        """Initialize OTP manager."""
        self.otps: Dict[str, OTPEntry] = {}
        logger.info("OTPManager initialized")

    def generate_otp(self, email: str) -> str:
        """
        Generate a new 6-digit OTP for email.

        Args:
            email: Email address

        Returns:
            6-digit OTP code
        """
        # Generate random 6-digit code
        code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])

        # Store OTP entry
        self.otps[email.lower()] = OTPEntry(code=code, email=email.lower())

        logger.info(f"Generated OTP for {email}")
        return code

    def verify_otp(self, email: str, code: str) -> tuple[bool, str]:
        """
        Verify OTP code for email.

        Args:
            email: Email address
            code: OTP code to verify

        Returns:
            Tuple of (success, message)
        """
        email = email.lower()

        # Check if OTP exists
        if email not in self.otps:
            return False, "No OTP found for this email. Please request a new one."

        otp_entry = self.otps[email]

        # Check if expired
        if otp_entry.is_expired():
            del self.otps[email]
            return False, "OTP has expired. Please request a new one."

        # Check if locked due to too many attempts
        if otp_entry.is_locked():
            del self.otps[email]
            return False, "Too many failed attempts. Please request a new OTP."

        # Increment attempts
        otp_entry.increment_attempts()

        # Verify code
        if otp_entry.code == code:
            # Success - remove OTP
            del self.otps[email]
            return True, "OTP verified successfully"
        else:
            remaining = otp_entry.max_attempts - otp_entry.attempts
            if remaining > 0:
                return False, f"Invalid OTP. {remaining} attempts remaining."
            else:
                del self.otps[email]
                return False, "Invalid OTP. Maximum attempts reached. Please request a new one."

    def cleanup_expired(self):
        """Remove expired OTP entries."""
        expired = [email for email, otp in self.otps.items() if otp.is_expired()]
        for email in expired:
            del self.otps[email]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired OTPs")


# Session Management
@dataclass
class Session:
    """
    User session with conversation history and authentication.

    Attributes:
        session_id: Unique session identifier
        messages: List of conversation messages
        attachments: List of attachments for this session
        created_at: Session creation timestamp
        last_activity: Last activity timestamp
        authenticated: Whether session is authenticated
        email: Authenticated email address (if authenticated)
        is_admin: Whether user has admin privileges
    """

    session_id: str
    messages: List[Dict] = field(default_factory=list)
    attachments: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    authenticated: bool = False
    email: Optional[str] = None
    is_admin: bool = False

    def authenticate(self, email: str, is_admin: bool = False):
        """
        Authenticate session with email.

        Args:
            email: Authenticated email address
            is_admin: Whether user has admin privileges
        """
        self.authenticated = True
        self.email = email.lower()
        self.is_admin = is_admin
        self.last_activity = datetime.now()
        admin_status = " (admin)" if is_admin else ""
        logger.info(f"Session {self.session_id} authenticated for {email}{admin_status}")

    def is_authenticated(self) -> bool:
        """Check if session is authenticated."""
        return self.authenticated and self.email is not None

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

admin_whitelist = WhitelistValidator(
    whitelist_file=settings.email_admin_whitelist_file,
    whitelist=settings.email_admin_whitelist,
    enabled=settings.email_admin_whitelist_enabled,
)

# Initialize admin managers
kb_manager = KnowledgeBaseManager()
document_processor = DocumentProcessor()
whitelist_manager = WhitelistManager()
document_manager = DocumentManager(
    kb_manager=kb_manager,
    document_processor=document_processor,
)
audit_logger = AdminAuditLogger()

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


def send_otp_email(email: str, otp_code: str) -> bool:
    """
    Send OTP code via email.

    Args:
        email: Recipient email address
        otp_code: 6-digit OTP code

    Returns:
        True if sent successfully, False otherwise
    """
    subject = f"{settings.instance_name} - Login Code"

    # Plain text version
    body_text = f"""Hello,

Your login code for {settings.instance_name} is: {otp_code}

This code will expire in 5 minutes.

If you did not request this code, please ignore this email.

Best regards,
{settings.instance_name}
{settings.organization}
"""

    # HTML version
    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .container {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 30px;
        }}
        .otp-code {{
            font-size: 32px;
            font-weight: bold;
            letter-spacing: 8px;
            color: #2563eb;
            text-align: center;
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border: 2px dashed #2563eb;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            font-size: 14px;
            color: #64748b;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Login Code for {settings.instance_name}</h2>
        <p>Hello,</p>
        <p>Your login code is:</p>
        <div class="otp-code">{otp_code}</div>
        <p><strong>This code will expire in 5 minutes.</strong></p>
        <p>If you did not request this code, please ignore this email.</p>
        <div class="footer">
            <p>Best regards,<br>
            <strong>{settings.instance_name}</strong><br>
            {settings.organization}</p>
        </div>
    </div>
</body>
</html>
"""

    try:
        success = email_sender.send_reply(
            to_address=email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        if success:
            logger.info(f"Sent OTP email to {email}")
        else:
            logger.error(f"Failed to send OTP email to {email}")
        return success
    except Exception as e:
        logger.error(f"Error sending OTP email: {e}")
        return False


# Authentication dependency
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


# API Endpoints

# Authentication Endpoints
@app.post("/api/auth/request-otp", response_model=AuthResponse)
async def request_otp(request: OTPRequest, background_tasks: BackgroundTasks):
    """
    Request OTP for email authentication.

    Args:
        request: OTP request with email
        background_tasks: Background task manager

    Returns:
        AuthResponse with success/failure message
    """
    email = request.email.lower()

    # Check if email is in query whitelist
    if not query_whitelist.is_allowed(email):
        logger.warning(f"OTP request denied for non-whitelisted email: {email}")
        return AuthResponse(
            success=False,
            message="Access denied. Your email address is not authorized to use this system. "
                   "Please contact your administrator if you believe this is an error.",
        )

    # Generate OTP
    otp_code = otp_manager.generate_otp(email)

    # Send OTP email in background
    background_tasks.add_task(send_otp_email, email, otp_code)
    background_tasks.add_task(otp_manager.cleanup_expired)

    logger.info(f"OTP requested for {email}")

    return AuthResponse(
        success=True,
        message=f"A login code has been sent to {email}. Please check your email and enter the code to continue.",
        email=email,
    )


@app.post("/api/auth/verify-otp", response_model=AuthResponse)
async def verify_otp(
    verify_request: OTPVerifyRequest,
    request: Request,
    response: Response,
):
    """
    Verify OTP and authenticate session.

    Args:
        verify_request: OTP verification request
        request: FastAPI request object
        response: FastAPI response object

    Returns:
        AuthResponse with success/failure message
    """
    email = verify_request.email.lower()
    otp_code = verify_request.otp_code

    # Verify OTP
    success, message = otp_manager.verify_otp(email, otp_code)

    if success:
        # Get or create session
        session_id = get_session_id(request)
        session = session_manager.get_or_create_session(session_id)

        # Check if user is admin
        is_admin = admin_whitelist.is_allowed(email)

        # Authenticate session with admin status
        session.authenticate(email, is_admin=is_admin)

        # Set session cookie
        set_session_cookie(response, session.session_id)

        admin_status = " (admin)" if is_admin else ""
        logger.info(f"Successfully authenticated {email}{admin_status}")

        return AuthResponse(
            success=True,
            message="Successfully authenticated! Redirecting to chat...",
            email=email,
        )
    else:
        logger.warning(f"Failed OTP verification for {email}: {message}")
        return AuthResponse(
            success=False,
            message=message,
        )


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """
    Logout and clear session.

    Args:
        request: FastAPI request object
        response: FastAPI response object

    Returns:
        Success message
    """
    session_id = get_session_id(request)
    if session_id:
        session_manager.delete_session(session_id)
        response.delete_cookie("session_id")
        logger.info(f"Logged out session {session_id}")

    return {"success": True, "message": "Logged out successfully"}


@app.get("/api/auth/status", response_model=AuthStatusResponse)
async def auth_status(request: Request):
    """
    Check authentication status.

    Args:
        request: FastAPI request object

    Returns:
        AuthStatusResponse with authentication status
    """
    session_id = get_session_id(request)
    if not session_id:
        return AuthStatusResponse(authenticated=False)

    session = session_manager.get_session(session_id)
    if not session or not session.is_authenticated():
        return AuthStatusResponse(authenticated=False)

    return AuthStatusResponse(
        authenticated=True,
        email=session.email,
        session_id=session.session_id,
        is_admin=session.is_admin,
    )


# Protected Endpoints (require authentication)
@app.get("/")
async def root():
    """Serve main web interface."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": f"Welcome to {settings.instance_name} API", "docs": "/docs"}


@app.get("/admin")
async def admin_panel():
    """
    Serve admin panel interface.

    Note: Authentication and admin privilege check is done client-side
    via JavaScript after page load.
    """
    admin_file = static_dir / "admin.html"
    if admin_file.exists():
        return FileResponse(admin_file)
    raise HTTPException(status_code=404, detail="Admin panel not found")


@app.post("/api/query", response_model=QueryResponse)
async def query(
    query_request: QueryRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    session: Session = Depends(require_auth),
):
    """
    Process a RAG query and return response.

    Requires authentication.

    Args:
        query_request: Query request with text and optional context
        request: FastAPI request object
        response: FastAPI response object
        background_tasks: Background task manager
        session: Authenticated session (injected by dependency)

    Returns:
        QueryResponse with answer, sources, and attachments
    """
    # Session is already authenticated via dependency
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
async def get_history(
    session: Session = Depends(require_auth),
):
    """
    Get conversation history for authenticated session.

    Requires authentication.

    Args:
        session: Authenticated session (injected by dependency)

    Returns:
        HistoryResponse with conversation messages
    """
    return HistoryResponse(
        session_id=session.session_id,
        messages=session.messages,
        created_at=session.created_at.isoformat(),
        last_activity=session.last_activity.isoformat(),
    )


@app.delete("/api/session")
async def clear_session(
    response: Response,
    session: Session = Depends(require_auth),
):
    """
    Clear session history and delete attachments.

    Requires authentication.

    Args:
        response: FastAPI response object
        session: Authenticated session (injected by dependency)

    Returns:
        Success message
    """
    if session_manager.delete_session(session.session_id):
        # Clear cookie
        response.delete_cookie("session_id")
        return {"success": True, "message": "Session cleared"}

    return {"success": False, "message": "Failed to clear session"}


@app.get("/api/attachments/{session_id}/{filename}")
async def download_attachment(
    session_id: str,
    filename: str,
    session: Session = Depends(require_auth),
):
    """
    Download attachment file.

    Requires authentication. Users can only download attachments from their own session.

    Args:
        session_id: Session ID
        filename: Attachment filename
        session: Authenticated session (injected by dependency)

    Returns:
        File download response

    Raises:
        HTTPException: If file not found or unauthorized
    """
    # Verify user is requesting their own session's attachments
    if session.session_id != session_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied. You can only download your own attachments."
        )

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
        raise HTTPException(status_code=500, detail=f"Error reading whitelist: {str(e)}")


@app.post("/api/admin/whitelists/{whitelist_type}/add", response_model=AdminActionResponse)
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


@app.delete("/api/admin/whitelists/{whitelist_type}/remove", response_model=AdminActionResponse)
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
        logger.info(
            f"Admin {session.email} listed documents ({len(documents)} found)"
        )
        return DocumentListResponse(
            documents=documents,
            total_count=len(documents),
        )
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing documents: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")


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
        doc = next((d for d in documents if d.get('file_hash') == file_hash), None)

        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found with hash: {file_hash}")

        # Only allow download of file-sourced documents (manual uploads or file ingestion)
        # Email-sourced documents don't have physical files to download
        allowed_source_types = ['manual', 'file']
        if doc.get('source_type') not in allowed_source_types:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot download documents from source type: {doc.get('source_type')}. Only manual/file uploads can be downloaded."
            )

        filename = doc['filename']
        file_path = document_manager.documents_path / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")

        # Log the download action
        audit_logger.log_action(
            session.email,
            "document_download",
            filename,
            "success",
            f"hash:{file_hash}"
        )

        logger.info(f"Admin {session.email} downloaded document: {filename}")

        # Determine content type based on file extension
        content_type = "application/octet-stream"
        if filename.endswith('.pdf'):
            content_type = "application/pdf"
        elif filename.endswith('.docx'):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif filename.endswith('.doc'):
            content_type = "application/msword"
        elif filename.endswith('.txt'):
            content_type = "text/plain"
        elif filename.endswith('.csv'):
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
        raise HTTPException(status_code=500, detail=f"Error downloading document: {str(e)}")


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
