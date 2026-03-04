"""
Authentication routes for the platform admin panel.

OTP-based auth scoped to PLATFORM_ADMIN_EMAILS only.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Request, Response

from src.platform_admin.models import (
    AdminAuthResponse,
    AdminAuthStatus,
    AdminOTPRequest,
    AdminOTPVerifyRequest,
)

logger = logging.getLogger(__name__)


@dataclass
class AdminSession:
    """
    Lightweight session for platform admin.

    No tenant context — just email and auth state.

    Attributes:
        email: Authenticated admin email.
        authenticated: Whether session is authenticated.
        created_at: Session creation timestamp.
        last_activity: Last activity timestamp.
    """

    email: str = ""
    authenticated: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


class AdminSessionManager:
    """
    Simple in-memory session store for platform admin.

    Attributes:
        sessions: Active sessions keyed by session ID.
        timeout: Session timeout in seconds.
    """

    def __init__(self, timeout: int = 3600):
        """
        Initialize admin session manager.

        Args:
            timeout: Session inactivity timeout in seconds.
        """
        self.sessions: Dict[str, AdminSession] = {}
        self.timeout = timeout

    def get(self, session_id: str) -> Optional[AdminSession]:
        """
        Get session by ID, checking expiry.

        Args:
            session_id: Session identifier.

        Returns:
            AdminSession or None if not found/expired.
        """
        session = self.sessions.get(session_id)
        if not session:
            return None
        if (datetime.now() - session.last_activity).total_seconds() > self.timeout:
            del self.sessions[session_id]
            return None
        session.last_activity = datetime.now()
        return session

    def create(self, session_id: str, email: str) -> AdminSession:
        """
        Create a new authenticated session.

        Args:
            session_id: Session identifier.
            email: Admin email address.

        Returns:
            New AdminSession.
        """
        session = AdminSession(email=email, authenticated=True)
        self.sessions[session_id] = session
        return session

    def delete(self, session_id: str) -> None:
        """
        Delete a session.

        Args:
            session_id: Session identifier.
        """
        self.sessions.pop(session_id, None)


def create_admin_auth_router(
    otp_manager,
    admin_session_manager: AdminSessionManager,
    admin_emails: list[str],
    email_sender,
    settings,
):
    """
    Create authentication router for platform admin.

    Args:
        otp_manager: OTP generation/verification manager.
        admin_session_manager: Admin session store.
        admin_emails: List of allowed platform admin emails.
        email_sender: Email sender for OTP delivery.
        settings: Application settings.

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix="/api/auth", tags=["admin-auth"])

    async def _send_otp_email(email: str, otp_code: str):
        """Send OTP code via email using shared helper."""
        from src.api.auth.otp_email import send_otp_email

        await send_otp_email(
            email_sender=email_sender,
            to_address=email,
            otp_code=otp_code,
            instance_name=settings.instance_name,
            admin_mode=True,
        )

    def _get_session_id(request: Request) -> Optional[str]:
        """Extract session ID from cookie."""
        return request.cookies.get("admin_session_id")

    @router.post("/request-otp", response_model=AdminAuthResponse)
    async def request_otp(request: AdminOTPRequest, background_tasks: BackgroundTasks):
        """
        Request OTP for platform admin login.

        Only accepts emails listed in PLATFORM_ADMIN_EMAILS.

        Args:
            request: OTP request with email.
            background_tasks: Background task manager.

        Returns:
            AdminAuthResponse.
        """
        email = request.email.lower()

        if email not in admin_emails:
            logger.warning(f"Admin OTP denied for non-admin email: {email}")
            return AdminAuthResponse(
                success=False,
                message="Access denied. This email is not authorized for platform admin.",
            )

        if settings.disable_otp_for_dev:
            logger.warning(f"SECURITY: OTP disabled for dev! Admin login for {email}")
            return AdminAuthResponse(
                success=True,
                message=f"Dev mode: OTP disabled. Enter any code for {email}.",
                email=email,
            )

        otp_code = otp_manager.generate_otp(email)
        background_tasks.add_task(_send_otp_email, email, otp_code)
        background_tasks.add_task(otp_manager.cleanup_expired)

        logger.info(f"Admin OTP requested for {email}")
        return AdminAuthResponse(
            success=True,
            message=f"Login code sent to {email}.",
            email=email,
        )

    @router.post("/verify-otp", response_model=AdminAuthResponse)
    async def verify_otp(
        verify_request: AdminOTPVerifyRequest,
        request_obj: Request,
        response: Response,
    ):
        """
        Verify OTP and create admin session.

        Args:
            verify_request: OTP verification request.
            request_obj: FastAPI request.
            response: FastAPI response (for setting cookie).

        Returns:
            AdminAuthResponse.
        """
        email = verify_request.email.lower()

        if email not in admin_emails:
            return AdminAuthResponse(success=False, message="Access denied.")

        if settings.disable_otp_for_dev:
            success, message = True, "Dev mode: OTP bypassed"
        else:
            success, message = otp_manager.verify_otp(email, verify_request.otp_code)

        if success:
            import uuid

            session_id = str(uuid.uuid4())
            admin_session_manager.create(session_id, email)
            response.set_cookie(
                key="admin_session_id",
                value=session_id,
                httponly=True,
                samesite="lax",
                max_age=admin_session_manager.timeout,
            )
            logger.info(f"Admin authenticated: {email}")
            return AdminAuthResponse(
                success=True,
                message="Authenticated. Redirecting to dashboard...",
                email=email,
            )

        logger.warning(f"Admin OTP verification failed for {email}: {message}")
        return AdminAuthResponse(success=False, message=message)

    @router.post("/logout")
    async def logout(request_obj: Request, response: Response):
        """
        Logout and clear admin session.

        Args:
            request_obj: FastAPI request.
            response: FastAPI response.

        Returns:
            Success message.
        """
        session_id = _get_session_id(request_obj)
        if session_id:
            admin_session_manager.delete(session_id)
        response.delete_cookie("admin_session_id")
        return {"success": True, "message": "Logged out"}

    @router.get("/status", response_model=AdminAuthStatus)
    async def auth_status(request_obj: Request):
        """
        Check admin authentication status.

        Args:
            request_obj: FastAPI request.

        Returns:
            AdminAuthStatus.
        """
        session_id = _get_session_id(request_obj)
        if not session_id:
            return AdminAuthStatus(authenticated=False)

        session = admin_session_manager.get(session_id)
        if not session or not session.authenticated:
            return AdminAuthStatus(authenticated=False)

        return AdminAuthStatus(authenticated=True, email=session.email)

    return router
