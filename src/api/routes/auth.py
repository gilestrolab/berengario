"""
Authentication routes for OTP-based authentication.

Handles OTP request, verification, logout, and auth status checking.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from src.api.models import (
    AuthResponse,
    AuthStatusResponse,
    OTPRequest,
    OTPVerifyRequest,
    TenantSelectRequest,
)

logger = logging.getLogger(__name__)


def create_auth_router(
    session_manager,
    otp_manager,
    query_whitelist,
    admin_whitelist,
    email_sender,
    get_session_id,
    set_session_cookie,
    settings,
    platform_db_manager=None,
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
        platform_db_manager: TenantDBManager for MT user lookups (optional)

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter(prefix="/api/auth", tags=["authentication"])

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
            email_sender.send_reply(
                to_address=email,
                subject=subject,
                body_text=body,
                body_html=None,
            )
            logger.info(f"OTP email sent to {email}")
        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {e}")

    def _lookup_tenant_users(email: str):
        """Look up TenantUser records for an email in the platform DB."""
        if not platform_db_manager:
            return []

        from src.platform.models import Tenant, TenantStatus, TenantUser

        with platform_db_manager.get_platform_session() as session:
            records = (
                session.query(TenantUser)
                .join(Tenant)
                .filter(
                    TenantUser.email == email,
                    Tenant.status == TenantStatus.ACTIVE,
                )
                .all()
            )
            # Convert to dicts before session closes
            return [
                {
                    "tenant_id": r.tenant_id,
                    "tenant_slug": r.tenant.slug,
                    "tenant_name": r.tenant.name,
                    "role": r.role.value if hasattr(r.role, "value") else r.role,
                }
                for r in records
            ]

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

        # MT mode: allow any email (unknown users enter onboarding flow)
        if settings.multi_tenant and platform_db_manager:
            # In MT mode, anyone can request OTP for onboarding or login
            pass
        else:
            # ST mode: check query whitelist
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

            # MT mode: look up tenant memberships and set on session
            if settings.multi_tenant and platform_db_manager:
                tenant_memberships = _lookup_tenant_users(email)

                if not tenant_memberships:
                    # Unknown email in MT mode: set onboarding state
                    session.authenticated = True
                    session.email = email
                    session.onboarding_email = email
                    session.onboarding_verified = True
                    session.last_activity = datetime.now()

                    set_session_cookie(response, session.session_id)

                    logger.info(
                        f"MT onboarding: verified email {email}, "
                        "no tenant membership found"
                    )
                    return AuthResponse(
                        success=True,
                        message="Email verified. Please create or join a team to continue.",
                        email=email,
                        requires_onboarding=True,
                    )

                # Authenticate first (admin flag set later by select_tenant)
                session.authenticate(email, is_admin=False)

                if len(tenant_memberships) == 1:
                    # Auto-select single tenant
                    t = tenant_memberships[0]
                    session.select_tenant(
                        tenant_id=t["tenant_id"],
                        tenant_slug=t["tenant_slug"],
                        tenant_name=t["tenant_name"],
                        role=t["role"],
                    )
                    logger.info(
                        f"Auto-selected tenant '{t['tenant_slug']}' for {email}"
                    )
                elif len(tenant_memberships) > 1:
                    # Multiple tenants: store for selection
                    session.available_tenants = tenant_memberships
                    logger.info(
                        f"User {email} has {len(tenant_memberships)} tenants, "
                        f"requires selection"
                    )

                set_session_cookie(response, session.session_id)

                return AuthResponse(
                    success=True,
                    message="Successfully authenticated! Redirecting to chat...",
                    email=email,
                )
            else:
                # ST mode: use file-based whitelists
                is_admin = admin_whitelist.is_allowed(email)
                session.authenticate(email, is_admin=is_admin)

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

    @router.post("/select-tenant")
    async def select_tenant(
        request: TenantSelectRequest,
        request_obj: Request,
    ):
        """
        Select active tenant for multi-tenant sessions.

        Called when a user belongs to multiple tenants and needs to pick one.

        Args:
            request: TenantSelectRequest with tenant_id
            request_obj: FastAPI request object

        Returns:
            Success response with tenant info
        """
        session_id = get_session_id(request_obj)
        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        session = session_manager.get_session(session_id)
        if not session or not session.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")

        # Find the requested tenant in available_tenants
        target = None
        for t in session.available_tenants:
            if t["tenant_id"] == request.tenant_id:
                target = t
                break

        if not target:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this tenant.",
            )

        session.select_tenant(
            tenant_id=target["tenant_id"],
            tenant_slug=target["tenant_slug"],
            tenant_name=target["tenant_name"],
            role=target["role"],
        )

        logger.info(f"User {session.email} selected tenant '{target['tenant_slug']}'")

        return {
            "success": True,
            "tenant_id": target["tenant_id"],
            "tenant_slug": target["tenant_slug"],
            "tenant_name": target["tenant_name"],
            "role": target["role"],
        }

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

        # Check if MT user needs to select a tenant
        requires_selection = bool(
            settings.multi_tenant
            and session.available_tenants
            and not session.tenant_id
        )

        return AuthStatusResponse(
            authenticated=True,
            email=session.email,
            session_id=session.session_id,
            is_admin=session.is_admin,
            tenant_id=session.tenant_id,
            tenant_name=session.tenant_name,
            tenant_slug=session.tenant_slug,
            role=session.role,
            requires_tenant_selection=requires_selection,
            available_tenants=(
                session.available_tenants
                if session.available_tenants and len(session.available_tenants) > 1
                else None
            ),
            onboarding_verified=session.onboarding_verified,
        )

    return router
