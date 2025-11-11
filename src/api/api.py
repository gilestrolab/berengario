"""
FastAPI web interface for RAG query testing.

Provides a REST API and web UI for real-time RAG queries with conversation threading.
"""

import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr

from src.api.admin.audit_logger import AdminAuditLogger
from src.api.admin.backup_manager import BackupManager
from src.api.admin.document_manager import DocumentManager
from src.api.admin.whitelist_manager import WhitelistManager
from src.config import settings
from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.email.conversation_manager import (
    ChannelType,
    MessageType,
    conversation_manager,
)
from src.email.email_sender import EmailSender
from src.email.whitelist_validator import WhitelistValidator
from src.rag.query_handler import QueryHandler
from src.rag.rag_engine import get_system_prompt

logger = logging.getLogger(__name__)


# Request/Response Models
class QueryRequest(BaseModel):
    """Request model for query endpoint."""

    query: str
    conversation_id: Optional[int] = None  # To continue existing conversation
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
    message_id: Optional[int] = None  # Database ID of reply message for feedback


class FeedbackRequest(BaseModel):
    """Request model for feedback submission."""

    message_id: int
    is_positive: bool
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    success: bool
    message: str


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


# Conversation Models
class ConversationListItem(BaseModel):
    """Single conversation item in list."""

    id: int
    thread_id: str
    channel: str
    sender: str
    created_at: str
    last_message_at: str
    message_count: int
    preview: Optional[str] = None
    subject: Optional[str] = None


class ConversationsResponse(BaseModel):
    """Response model for conversations list."""

    conversations: List[ConversationListItem]
    total_count: int


class ConversationMessagesResponse(BaseModel):
    """Response model for conversation messages."""

    conversation_id: int
    thread_id: str
    channel: str
    messages: List[Dict]


class ConversationSearchResponse(BaseModel):
    """Response model for conversation search."""

    results: List[ConversationListItem]
    query: str
    total_results: int


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


class UsageAnalyticsResponse(BaseModel):
    """Response model for usage analytics."""

    date_range: Dict[str, str]
    overview: Dict
    daily_stats: List[Dict]
    user_activity: List[Dict]
    channel_breakdown: Dict[str, int]


class UserQueriesResponse(BaseModel):
    """Response model for user query details."""

    sender: str
    queries: List[Dict]
    total_count: int


class FeedbackAnalyticsResponse(BaseModel):
    """Response model for feedback analytics."""

    date_range: Dict[str, str]
    overview: Dict  # total_feedback, positive_count, negative_count, positive_rate
    negative_responses: List[Dict]  # Low-rated responses with details


class TopicClusteringResponse(BaseModel):
    """Response model for topic clustering."""

    topics: List[Dict]
    total_queries: int
    clustered_queries: int


class DocumentDeleteRequest(BaseModel):
    """Request model for document deletion."""

    file_hash: str
    archive: bool = True


class CrawlRequest(BaseModel):
    """Request model for URL crawling."""

    url: str
    crawl_depth: int = 1


class CrawledUrlResponse(BaseModel):
    """Response model for crawled URL list."""

    urls: List[Dict]
    total_count: int


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
    expires_at: datetime = field(
        default_factory=lambda: datetime.now() + timedelta(minutes=5)
    )
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
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

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
                return (
                    False,
                    "Invalid OTP. Maximum attempts reached. Please request a new one.",
                )

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
        logger.info(
            f"Session {self.session_id} authenticated for {email}{admin_status}"
        )

    def is_authenticated(self) -> bool:
        """Check if session is authenticated."""
        return self.authenticated and self.email is not None

    def add_message(
        self,
        role: str,
        content: str,
        sources: Optional[List] = None,
        attachments: Optional[List] = None,
    ):
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

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
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

    # Development mode: Skip OTP email sending
    if settings.disable_otp_for_dev:
        logger.warning(
            f"⚠️ SECURITY WARNING: OTP disabled for development! "
            f"Allowing login for {email} without email verification. "
            f"DO NOT USE IN PRODUCTION!"
        )
        return AuthResponse(
            success=True,
            message=f"Development mode: OTP disabled. Enter any code to login as {email}.",
            email=email,
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

    # Development mode: Skip OTP verification
    if settings.disable_otp_for_dev:
        logger.warning(
            f"⚠️ SECURITY WARNING: OTP verification bypassed for development! "
            f"Authenticating {email} without verification. DO NOT USE IN PRODUCTION!"
        )
        success = True
        message = "Development mode: OTP verification bypassed"
    else:
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
@app.get("/feedback")
async def feedback_page(request: Request):
    """Serve feedback page for email link clicks."""
    feedback_file = static_dir / "feedback.html"
    if feedback_file.exists():
        return FileResponse(feedback_file)
    raise HTTPException(status_code=404, detail="Feedback page not found")


@app.post("/api/feedback/email", response_model=FeedbackResponse)
async def submit_email_feedback(
    feedback: dict,
):
    """
    Submit feedback from email link (no authentication required).

    This endpoint is for users clicking feedback links in emails.
    It validates the token before accepting feedback.

    Args:
        feedback: Dict with token, message_id, is_positive, optional comment

    Returns:
        FeedbackResponse with success status
    """
    try:
        from src.email.db_models import ConversationMessage, ResponseFeedback
        from src.email.email_sender import decode_feedback_token

        # Extract fields
        token = feedback.get("token")
        message_id = feedback.get("message_id")
        is_positive = feedback.get("is_positive")
        comment = feedback.get("comment")

        if not token or message_id is None:
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Decode and validate token
        decoded_message_id = decode_feedback_token(token)
        if decoded_message_id != message_id:
            raise HTTPException(status_code=400, detail="Invalid feedback token")

        # Verify message exists and is a reply
        with conversation_manager.db_manager.get_session() as db_session:
            message = (
                db_session.query(ConversationMessage)
                .filter(ConversationMessage.id == message_id)
                .first()
            )

            if not message:
                raise HTTPException(status_code=404, detail="Message not found")

            if message.message_type != MessageType.REPLY:
                raise HTTPException(
                    status_code=400,
                    detail="Can only provide feedback on assistant replies",
                )

            # Get user email from the conversation
            user_email = message.conversation.sender

            # Check if feedback already exists for this message from this user
            existing_feedback = (
                db_session.query(ResponseFeedback)
                .filter(
                    ResponseFeedback.message_id == message_id,
                    ResponseFeedback.user_email == user_email,
                )
                .first()
            )

            if existing_feedback:
                # Update existing feedback
                existing_feedback.is_positive = is_positive
                existing_feedback.comment = comment
                existing_feedback.submitted_at = datetime.utcnow()
                db_session.commit()
                logger.info(
                    f"Updated email feedback for message {message_id} from {user_email}"
                )
            else:
                # Create new feedback
                new_feedback = ResponseFeedback(
                    message_id=message_id,
                    is_positive=is_positive,
                    comment=comment,
                    user_email=user_email,
                    channel=message.conversation.channel,
                )
                db_session.add(new_feedback)
                db_session.commit()
                logger.info(
                    f"Stored email feedback for message {message_id} from {user_email}"
                )

        return FeedbackResponse(success=True, message="Feedback submitted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting email feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


@app.get("/")
async def root(request: Request):
    """Serve main web interface."""
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

    Note: Authentication and admin privilege check is done client-side
    via JavaScript after page load.
    """
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

    user_identifier = (
        session.email
        if hasattr(session, "email") and session.email
        else f"web_user_{session.session_id[:8]}"
    )

    # Determine thread_id: use existing conversation or create new
    thread_id = None
    channel = ChannelType.WEBCHAT

    if query_request.conversation_id:
        # Continue existing conversation
        from src.email.db_models import Conversation

        with conversation_manager.db_manager.get_session() as db_session:
            existing_conv = (
                db_session.query(Conversation)
                .filter(Conversation.id == query_request.conversation_id)
                .first()
            )

            if not existing_conv:
                raise HTTPException(status_code=404, detail="Conversation not found")

            # Verify user owns this conversation
            if existing_conv.sender != user_identifier:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. You can only continue your own conversations.",
                )

            thread_id = existing_conv.thread_id
            channel = existing_conv.channel

            logger.info(
                f"Continuing conversation {query_request.conversation_id} (thread: {thread_id})"
            )
    else:
        # Create new conversation with unique thread_id
        import uuid
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        thread_id = f"webchat_{session.session_id[:8]}_{timestamp}_{unique_id}"

        logger.info(f"Created new conversation thread: {thread_id}")

    # Store user query in conversation database
    conversation_manager.add_message(
        thread_id=thread_id,
        message_type=MessageType.QUERY,
        content=query_request.query,
        sender=user_identifier,
        channel=channel,
    )

    # Add user message to in-memory session history
    session.add_message("user", query_request.query)

    # Build conversation history from session messages for context
    conversation_history = conversation_manager.format_conversation_context(
        thread_id=thread_id,
        max_messages=10,  # Last 10 messages for context
    )

    try:
        # Process query through RAG engine with conversation history
        # Pass admin status from session for tool access control
        context = query_request.context or {}
        context["conversation_history"] = conversation_history

        result = query_handler.process_query(
            query_text=query_request.query,
            user_email=user_identifier,
            is_admin=session.is_admin if hasattr(session, "is_admin") else False,
            context=context,
        )

        if not result["success"]:
            error_response = f"Error: {result.get('error', 'Unknown error')}"
            session.add_message("assistant", error_response)

            # Store error response in conversation database
            conversation_manager.add_message(
                thread_id=thread_id,
                message_type=MessageType.REPLY,
                content=error_response,
                sender=settings.instance_name,
                channel=channel,
            )

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
                    "content_type": attachment.get(
                        "content_type", "application/octet-stream"
                    ),
                }
                attachment_urls.append(attachment_url)

        # Add assistant response to in-memory session history
        session.add_message(
            "assistant",
            result["response"],
            sources=result["sources"],
            attachments=attachment_urls,
        )

        # Store assistant response in conversation database
        reply_message_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.REPLY,
            content=result["response"],
            sender=settings.instance_name,
            channel=channel,
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
            message_id=reply_message_id,
        )

    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        error_msg = str(e)
        error_response = f"Error: {error_msg}"
        session.add_message("assistant", error_response)

        # Store exception error in conversation database
        conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.REPLY,
            content=error_response,
            sender=settings.instance_name,
            channel=channel,
        )

        return QueryResponse(
            success=False,
            error=error_msg,
            timestamp=datetime.now().isoformat(),
            session_id=session.session_id,
        )


@app.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: FeedbackRequest,
    session: Session = Depends(require_auth),
):
    """
    Submit feedback on an assistant response.

    Requires authentication.

    Args:
        feedback: Feedback data (message_id, is_positive, optional comment)
        session: Authenticated session (injected by dependency)

    Returns:
        FeedbackResponse with success status
    """
    try:
        from src.email.db_models import ConversationMessage, ResponseFeedback

        # Get user email from session
        user_email = (
            session.email
            if hasattr(session, "email") and session.email
            else f"web_user_{session.session_id[:8]}"
        )

        # Verify message exists and is a reply
        with conversation_manager.db_manager.get_session() as db_session:
            message = (
                db_session.query(ConversationMessage)
                .filter(ConversationMessage.id == feedback.message_id)
                .first()
            )

            if not message:
                raise HTTPException(status_code=404, detail="Message not found")

            if message.message_type != MessageType.REPLY:
                raise HTTPException(
                    status_code=400,
                    detail="Can only provide feedback on assistant replies",
                )

            # Check if feedback already exists for this message from this user
            existing_feedback = (
                db_session.query(ResponseFeedback)
                .filter(
                    ResponseFeedback.message_id == feedback.message_id,
                    ResponseFeedback.user_email == user_email,
                )
                .first()
            )

            if existing_feedback:
                # Update existing feedback
                existing_feedback.is_positive = feedback.is_positive
                existing_feedback.comment = feedback.comment
                existing_feedback.submitted_at = datetime.utcnow()
                db_session.commit()
                logger.info(
                    f"Updated feedback for message {feedback.message_id} from {user_email}"
                )
            else:
                # Create new feedback
                new_feedback = ResponseFeedback(
                    message_id=feedback.message_id,
                    is_positive=feedback.is_positive,
                    comment=feedback.comment,
                    user_email=user_email,
                    channel=message.conversation.channel,
                )
                db_session.add(new_feedback)
                db_session.commit()
                logger.info(
                    f"Stored feedback for message {feedback.message_id} from {user_email}"
                )

        return FeedbackResponse(success=True, message="Feedback submitted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


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


@app.get("/api/conversations", response_model=ConversationsResponse)
async def list_conversations(
    session: Session = Depends(require_auth),
):
    """
    Get list of all conversations for authenticated user.

    Returns conversations from database (both email and webchat) sorted by
    most recent activity.

    Requires authentication.

    Args:
        session: Authenticated session (injected by dependency)

    Returns:
        ConversationsResponse with list of conversations
    """
    from sqlalchemy import desc, func

    from src.email.db_models import Conversation, ConversationMessage

    user_email = session.email if hasattr(session, "email") and session.email else None
    if not user_email:
        return ConversationsResponse(conversations=[], total_count=0)

    with conversation_manager.db_manager.get_session() as db_session:
        # Query conversations for this user, ordered by most recent
        conversations_query = (
            db_session.query(Conversation)
            .filter(Conversation.sender == user_email)
            .order_by(desc(Conversation.last_message_at))
        )

        conversations = conversations_query.all()
        conversation_items = []

        for conv in conversations:
            # Get message count
            message_count = (
                db_session.query(func.count(ConversationMessage.id))
                .filter(ConversationMessage.conversation_id == conv.id)
                .scalar()
            ) or 0

            # Get first message for preview
            first_message = (
                db_session.query(ConversationMessage)
                .filter(ConversationMessage.conversation_id == conv.id)
                .order_by(ConversationMessage.message_order)
                .first()
            )

            preview = None
            subject = None
            if first_message:
                # Truncate preview to 100 chars
                preview = (
                    (first_message.content[:100] + "...")
                    if len(first_message.content) > 100
                    else first_message.content
                )
                subject = first_message.subject

            conversation_items.append(
                ConversationListItem(
                    id=conv.id,
                    thread_id=conv.thread_id,
                    channel=(
                        conv.channel.value
                        if hasattr(conv.channel, "value")
                        else str(conv.channel)
                    ),
                    sender=conv.sender,
                    created_at=conv.created_at.isoformat(),
                    last_message_at=conv.last_message_at.isoformat(),
                    message_count=message_count,
                    preview=preview,
                    subject=subject,
                )
            )

        return ConversationsResponse(
            conversations=conversation_items,
            total_count=len(conversation_items),
        )


@app.get(
    "/api/conversations/{conversation_id}", response_model=ConversationMessagesResponse
)
async def get_conversation_messages(
    conversation_id: int,
    session: Session = Depends(require_auth),
):
    """
    Get all messages for a specific conversation.

    Requires authentication. Users can only access their own conversations.

    Args:
        conversation_id: Conversation ID
        session: Authenticated session (injected by dependency)

    Returns:
        ConversationMessagesResponse with all messages

    Raises:
        HTTPException: If conversation not found or unauthorized
    """
    from src.email.db_models import Conversation, ConversationMessage

    user_email = session.email if hasattr(session, "email") and session.email else None
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with conversation_manager.db_manager.get_session() as db_session:
        # Get conversation and verify ownership
        conversation = (
            db_session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.sender != user_email:
            raise HTTPException(
                status_code=403,
                detail="Access denied. You can only view your own conversations.",
            )

        # Get all messages ordered by message_order
        messages = (
            db_session.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.message_order)
            .all()
        )

        # Convert to dictionaries
        message_list = [
            {
                "id": msg.id,
                "role": "user" if msg.message_type.value == "query" else "assistant",
                "content": msg.content,
                "sender": msg.sender,
                "subject": msg.subject,
                "timestamp": msg.timestamp.isoformat(),
                "message_order": msg.message_order,
                "rating": msg.rating,
            }
            for msg in messages
        ]

        return ConversationMessagesResponse(
            conversation_id=conversation.id,
            thread_id=conversation.thread_id,
            channel=(
                conversation.channel.value
                if hasattr(conversation.channel, "value")
                else str(conversation.channel)
            ),
            messages=message_list,
        )


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    session: Session = Depends(require_auth),
):
    """
    Delete a conversation and all its messages.

    Requires authentication. Users can only delete their own conversations.

    Args:
        conversation_id: Conversation ID to delete
        session: Authenticated session (injected by dependency)

    Returns:
        Success message

    Raises:
        HTTPException: If conversation not found or unauthorized
    """
    from src.email.db_models import Conversation

    user_email = session.email if hasattr(session, "email") and session.email else None
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with conversation_manager.db_manager.get_session() as db_session:
        # Get conversation and verify ownership
        conversation = (
            db_session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if conversation.sender != user_email:
            raise HTTPException(
                status_code=403,
                detail="Access denied. You can only delete your own conversations.",
            )

        # Delete conversation (messages cascade delete automatically)
        thread_id = conversation.thread_id
        db_session.delete(conversation)
        db_session.commit()

        logger.info(
            f"User {user_email} deleted conversation {conversation_id} (thread: {thread_id})"
        )

        return {"success": True, "message": "Conversation deleted"}


@app.get("/api/conversations/search", response_model=ConversationSearchResponse)
async def search_conversations(
    q: str,
    session: Session = Depends(require_auth),
):
    """
    Search conversations by content, subject, or sender.

    Requires authentication. Only searches user's own conversations.

    Args:
        q: Search query string
        session: Authenticated session (injected by dependency)

    Returns:
        ConversationSearchResponse with matching conversations
    """
    from sqlalchemy import desc, func, or_

    from src.email.db_models import Conversation, ConversationMessage

    user_email = session.email if hasattr(session, "email") and session.email else None
    if not user_email:
        return ConversationSearchResponse(results=[], query=q, total_results=0)

    if not q or len(q.strip()) < 2:
        return ConversationSearchResponse(results=[], query=q, total_results=0)

    search_term = f"%{q}%"

    with conversation_manager.db_manager.get_session() as db_session:
        # Find conversations where message content or subject matches search
        matching_conv_ids = (
            db_session.query(ConversationMessage.conversation_id)
            .distinct()
            .filter(
                or_(
                    ConversationMessage.content.ilike(search_term),
                    ConversationMessage.subject.ilike(search_term),
                )
            )
            .subquery()
        )

        # Get conversations that match
        conversations_query = (
            db_session.query(Conversation)
            .filter(
                Conversation.sender == user_email,
                Conversation.id.in_(matching_conv_ids),
            )
            .order_by(desc(Conversation.last_message_at))
        )

        conversations = conversations_query.all()
        results = []

        for conv in conversations:
            # Get message count
            message_count = (
                db_session.query(func.count(ConversationMessage.id))
                .filter(ConversationMessage.conversation_id == conv.id)
                .scalar()
            ) or 0

            # Get first matching message for context
            matching_message = (
                db_session.query(ConversationMessage)
                .filter(
                    ConversationMessage.conversation_id == conv.id,
                    or_(
                        ConversationMessage.content.ilike(search_term),
                        ConversationMessage.subject.ilike(search_term),
                    ),
                )
                .first()
            )

            preview = None
            subject = None
            if matching_message:
                # Show snippet around match
                content = matching_message.content
                preview = (content[:100] + "...") if len(content) > 100 else content
                subject = matching_message.subject

            results.append(
                ConversationListItem(
                    id=conv.id,
                    thread_id=conv.thread_id,
                    channel=(
                        conv.channel.value
                        if hasattr(conv.channel, "value")
                        else str(conv.channel)
                    ),
                    sender=conv.sender,
                    created_at=conv.created_at.isoformat(),
                    last_message_at=conv.last_message_at.isoformat(),
                    message_count=message_count,
                    preview=preview,
                    subject=subject,
                )
            )

        return ConversationSearchResponse(
            results=results,
            query=q,
            total_results=len(results),
        )


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
            detail="Access denied. You can only download your own attachments.",
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

            # Save permanent copy to data/documents/ first
            documents_dir = Path("data/documents")
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
