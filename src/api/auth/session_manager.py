"""
Session management for web authentication.

Handles user sessions, authentication state, and conversation history.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from src.config import settings

logger = logging.getLogger(__name__)


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
