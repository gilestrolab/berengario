"""
Onboarding routes for multi-tenant self-service.

Handles tenant creation, invite code validation, and joining existing tenants.
All endpoints require either an onboarding-verified session or are public.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from src.api.models import (
    CreateTenantRequest,
    CreateTenantResponse,
    JoinTenantRequest,
    JoinTenantResponse,
    SlugCheckResponse,
    ValidateCodeRequest,
    ValidateCodeResponse,
)

logger = logging.getLogger(__name__)


def create_onboarding_router(
    platform_db_manager,
    session_manager,
    get_session_id,
    set_session_cookie,
    settings,
    key_manager=None,
    email_sender=None,
):
    """
    Create onboarding router for multi-tenant self-service.

    Args:
        platform_db_manager: TenantDBManager for platform DB access.
        session_manager: Session management instance.
        get_session_id: Function to extract session ID from request.
        set_session_cookie: Function to set session cookie.
        settings: Application settings.
        key_manager: DatabaseKeyManager for per-tenant encryption (optional).
        email_sender: EmailSender instance for welcome emails (optional).

    Returns:
        Configured APIRouter instance.
    """
    router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

    def _get_onboarding_session(request: Request):
        """Get session that has passed onboarding email verification."""
        session_id = get_session_id(request)
        if not session_id:
            raise HTTPException(
                status_code=403,
                detail="Not authenticated. Please verify your email first.",
            )
        session = session_manager.get_session(session_id)
        if not session or not session.onboarding_verified:
            raise HTTPException(
                status_code=403,
                detail="Email not verified for onboarding. Please verify first.",
            )
        return session

    @router.post("/create-tenant", response_model=CreateTenantResponse)
    async def create_tenant(
        body: CreateTenantRequest,
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
    ):
        """
        Create a new tenant (requires onboarding-verified session).

        The authenticated user becomes the tenant admin.
        """
        session = _get_onboarding_session(request)
        email = session.onboarding_email

        from src.platform.provisioning import TenantProvisioner, generate_slug
        from src.platform.storage import create_storage_backend

        # Generate slug from name if not provided
        slug = body.slug
        if not slug:
            slug = generate_slug(body.name)

        # Validate slug
        if not TenantProvisioner.validate_slug(slug):
            return CreateTenantResponse(
                success=False,
                message=f"Invalid slug '{slug}'. Must be 2-63 chars, "
                "lowercase alphanumeric with optional hyphens.",
            )

        try:
            storage = create_storage_backend()
            provisioner = TenantProvisioner(
                db_manager=platform_db_manager,
                storage=storage,
                key_manager=key_manager,
            )

            tenant = provisioner.create_tenant(
                slug=slug,
                name=body.name,
                admin_email=email,
                description=body.description,
                organization=body.organization,
            )

            # Select the new tenant in the session
            session.onboarding_email = None
            session.onboarding_verified = False
            session.select_tenant(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                tenant_name=tenant.name,
                role="admin",
            )

            set_session_cookie(response, session.session_id)

            logger.info(f"Tenant '{slug}' created by {email} via onboarding")

            # Send welcome email to the new admin
            if email_sender:
                from src.email.email_sender import send_welcome_email

                background_tasks.add_task(
                    send_welcome_email,
                    sender_instance=email_sender,
                    to_email=email,
                    role="admin",
                    instance_name=body.name,
                    organization=body.organization or "",
                    instance_description=body.description or "",
                )

            return CreateTenantResponse(
                success=True,
                message="Team created successfully!",
                tenant_slug=tenant.slug,
                tenant_name=tenant.name,
                tenant_id=tenant.id,
            )

        except ValueError as e:
            return CreateTenantResponse(success=False, message=str(e))
        except Exception as e:
            logger.error(f"Failed to create tenant: {e}", exc_info=True)
            return CreateTenantResponse(
                success=False,
                message="Failed to create team. Please try again.",
            )

    @router.post("/validate-code", response_model=ValidateCodeResponse)
    async def validate_code(body: ValidateCodeRequest):
        """
        Validate an invite code (public endpoint).

        Returns tenant name and whether approval is required.
        Does not expose sensitive information.
        """
        from src.platform.models import Tenant, TenantStatus

        code = body.code.upper().strip()

        with platform_db_manager.get_platform_session() as db_session:
            tenant = (
                db_session.query(Tenant)
                .filter(
                    Tenant.invite_code == code,
                    Tenant.status == TenantStatus.ACTIVE,
                )
                .first()
            )

            if not tenant:
                return ValidateCodeResponse(valid=False)

            return ValidateCodeResponse(
                valid=True,
                tenant_name=tenant.name,
                requires_approval=tenant.join_approval_required,
            )

    @router.post("/join-tenant", response_model=JoinTenantResponse)
    async def join_tenant(
        body: JoinTenantRequest,
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
    ):
        """
        Join a tenant via invite code (requires onboarding-verified session).

        If the tenant requires approval, a join request is created.
        Otherwise, the user is added directly as a querier.
        """
        session = _get_onboarding_session(request)
        email = session.onboarding_email

        from src.platform.models import (
            JoinRequest,
            JoinRequestStatus,
            Tenant,
            TenantStatus,
            TenantUser,
            TenantUserRole,
        )

        code = body.code.upper().strip()

        with platform_db_manager.get_platform_session() as db_session:
            tenant = (
                db_session.query(Tenant)
                .filter(
                    Tenant.invite_code == code,
                    Tenant.status == TenantStatus.ACTIVE,
                )
                .first()
            )

            if not tenant:
                return JoinTenantResponse(
                    success=False,
                    message="Invalid or expired invite code.",
                )

            # Check if user already belongs to this tenant
            existing = (
                db_session.query(TenantUser)
                .filter(
                    TenantUser.email == email,
                    TenantUser.tenant_id == tenant.id,
                )
                .first()
            )
            if existing:
                return JoinTenantResponse(
                    success=False,
                    message="You are already a member of this team.",
                )

            if tenant.join_approval_required:
                # Check for existing pending request
                pending = (
                    db_session.query(JoinRequest)
                    .filter(
                        JoinRequest.email == email,
                        JoinRequest.tenant_id == tenant.id,
                        JoinRequest.status == JoinRequestStatus.PENDING,
                    )
                    .first()
                )
                if pending:
                    return JoinTenantResponse(
                        success=True,
                        message="You already have a pending request for this team.",
                        pending_approval=True,
                    )

                # Create join request
                join_request = JoinRequest(
                    email=email,
                    tenant_id=tenant.id,
                )
                db_session.add(join_request)
                db_session.flush()

                logger.info(f"Join request created: {email} → {tenant.slug}")
                return JoinTenantResponse(
                    success=True,
                    message="Your request to join has been submitted. "
                    "An admin will review it shortly.",
                    pending_approval=True,
                )
            else:
                # Direct join — create TenantUser
                user = TenantUser(
                    email=email,
                    tenant_id=tenant.id,
                    role=TenantUserRole.QUERIER,
                )
                db_session.add(user)
                db_session.flush()

                # Clear onboarding state and select tenant
                session.onboarding_email = None
                session.onboarding_verified = False
                session.select_tenant(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    tenant_name=tenant.name,
                    role="querier",
                )

                set_session_cookie(response, session.session_id)

                logger.info(
                    f"User {email} joined tenant '{tenant.slug}' via invite code"
                )

                # Send welcome email to new member
                if email_sender:
                    from src.email.email_sender import (
                        fetch_tenant_welcome_params,
                        send_welcome_email,
                    )

                    params = fetch_tenant_welcome_params(
                        tenant.id, db_session=db_session
                    )

                    background_tasks.add_task(
                        send_welcome_email,
                        sender_instance=email_sender,
                        to_email=email,
                        role="querier",
                        **params,
                    )

                return JoinTenantResponse(
                    success=True,
                    message=f"Welcome to {tenant.name}!",
                    joined=True,
                )

    @router.get("/slug-check", response_model=SlugCheckResponse)
    async def slug_check(slug: str):
        """
        Check if a slug is available (public endpoint).

        Returns availability and a suggestion if taken.
        """
        from src.platform.models import Tenant
        from src.platform.provisioning import TenantProvisioner

        slug = slug.lower().strip()

        if not TenantProvisioner.validate_slug(slug):
            return SlugCheckResponse(
                available=False,
                suggestion=None,
            )

        with platform_db_manager.get_platform_session() as db_session:
            existing = db_session.query(Tenant).filter(Tenant.slug == slug).first()

            if not existing:
                return SlugCheckResponse(available=True)

            # Generate suggestion by appending a number
            for i in range(2, 100):
                candidate = f"{slug}-{i}"
                if len(candidate) > 63:
                    break
                exists = (
                    db_session.query(Tenant).filter(Tenant.slug == candidate).first()
                )
                if not exists:
                    return SlugCheckResponse(
                        available=False,
                        suggestion=candidate,
                    )

            return SlugCheckResponse(available=False)

    return router
