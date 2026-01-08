"""
Authentication routes for OTP-based authentication.

Handles OTP request, verification, logout, and auth status checking.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response

from src.api.models import (
    AuthResponse,
    AuthStatusResponse,
    OTPRequest,
    OTPVerifyRequest,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/auth", tags=["authentication"])


def create_auth_router(
    session_manager,
    otp_manager,
    query_whitelist,
    admin_whitelist,
    email_sender,
    get_session_id,
    set_session_cookie,
    settings,
):
    """
    Create authentication router with dependency injection.

    Args:
        session_manager: Session management instance
        otp_manager: OTP management instance
        query_whitelist: Query whitelist validator
        admin_whitelist: Admin whitelist validator
        email_sender: Email sender instance
        get_session_id: Function to extract session ID from request
        set_session_cookie: Function to set session cookie
        settings: Application settings

    Returns:
        Configured APIRouter instance
    """

    async def send_otp_email(email: str, otp_code: str):
        """Send OTP code via email."""
        subject = f"{settings.instance_name} - Your Login Code"
        body = f"""
Your one-time login code is:

{otp_code}

This code will expire in 5 minutes.

If you didn't request this code, please ignore this email.

---
{settings.instance_name}
{settings.organization}
"""
        try:
            await email_sender.send_reply(
                to_email=email,
                subject=subject,
                body_text=body,
                body_html=None,
            )
            logger.info(f"OTP email sent to {email}")
        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {e}")

    @router.post("/request-otp", response_model=AuthResponse)
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

    @router.post("/verify-otp", response_model=AuthResponse)
    async def verify_otp(
        verify_request: OTPVerifyRequest,
        request_obj: Request,
        response: Response,
    ):
        """
        Verify OTP and authenticate session.

        Args:
            verify_request: OTP verification request
            request_obj: FastAPI request object
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
            session_id = get_session_id(request_obj)
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

    @router.post("/logout")
    async def logout(request_obj: Request, response: Response):
        """
        Logout and clear session.

        Args:
            request_obj: FastAPI request object
            response: FastAPI response object

        Returns:
            Success message
        """
        session_id = get_session_id(request_obj)
        if session_id:
            session_manager.delete_session(session_id)
            response.delete_cookie("session_id")
            logger.info(f"Logged out session {session_id}")

        return {"success": True, "message": "Logged out successfully"}

    @router.get("/status", response_model=AuthStatusResponse)
    async def auth_status(request_obj: Request):
        """
        Check authentication status.

        Args:
            request_obj: FastAPI request object

        Returns:
            AuthStatusResponse with authentication status
        """
        session_id = get_session_id(request_obj)
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

    return router
