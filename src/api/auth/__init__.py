"""
Authentication module for RAGInbox API.

Provides OTP management, session management, and authentication dependencies.
"""

from src.api.auth.dependencies import get_session_id, set_session_cookie
from src.api.auth.otp_manager import OTPManager
from src.api.auth.session_manager import Session, SessionManager

__all__ = [
    "OTPManager",
    "Session",
    "SessionManager",
    "get_session_id",
    "set_session_cookie",
]
