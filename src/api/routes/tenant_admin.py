"""
Tenant administration routes for multi-tenant mode.

Handles invite code management, join request approval/rejection,
and tenant-level settings. All endpoints require admin privileges.
"""

import io
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.models import (
    AdminActionResponse,
    JoinRequestActionResponse,
    TenantSettingsRequest,
)

logger = logging.getLogger(__name__)


def create_tenant_admin_router(
    platform_db_manager,
    require_admin,
    session_manager,
    get_session_id,
    settings,
    email_sender=None,
):
    """
    Create tenant admin router with dependency injection.

    Args:
        platform_db_manager: TenantDBManager for platform DB access.
        require_admin: FastAPI dependency that checks admin status.
        session_manager: Session management instance.
        get_session_id: Function to extract session ID from request.
        settings: Application settings.
        email_sender: EmailSender instance for welcome emails (optional).

    Returns:
        Configured APIRouter instance.
    """
    router = APIRouter(
        prefix="/api/admin/tenant",
        tags=["tenant-admin"],
    )

    @router.get("/details")
    def get_tenant_details(admin_session=Depends(require_admin)):
        """Get tenant details for the settings form."""

        from src.platform.models import Tenant

        with platform_db_manager.get_platform_session() as db_session:
            tenant = (
                db_session.query(Tenant)
                .filter(Tenant.id == admin_session.tenant_id)
                .first()
            )
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            return {
                "name": tenant.name,
                "description": tenant.description or "",
                "organization": tenant.organization or "",
                "slug": tenant.slug,
                "email_address": tenant.email_address or "",
            }

    @router.get("/invite")
    def get_invite_info(admin_session=Depends(require_admin)):
        """Get invite code and join settings for the current tenant."""

        from src.platform.models import Tenant

        with platform_db_manager.get_platform_session() as db_session:
            tenant = (
                db_session.query(Tenant)
                .filter(Tenant.id == admin_session.tenant_id)
                .first()
            )
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            return {
                "invite_code": tenant.invite_code,
                "join_approval_required": tenant.join_approval_required,
                "tenant_name": tenant.name,
            }

    @router.post("/invite/regenerate")
    def regenerate_invite_code(admin_session=Depends(require_admin)):
        """Generate a new invite code, invalidating the old one."""

        from src.platform.models import Tenant

        with platform_db_manager.get_platform_session() as db_session:
            tenant = (
                db_session.query(Tenant)
                .filter(Tenant.id == admin_session.tenant_id)
                .first()
            )
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            new_code = Tenant.generate_invite_code()
            tenant.invite_code = new_code
            tenant.updated_at = datetime.utcnow()

            logger.info(
                f"Invite code regenerated for tenant "
                f"'{admin_session.tenant_slug}' by {admin_session.email}"
            )

            return {"invite_code": new_code}

    @router.put("/settings")
    def update_tenant_settings(
        body: TenantSettingsRequest,
        admin_session=Depends(require_admin),
    ):
        """Update tenant settings (join policy, description, organization)."""

        from src.platform.models import Tenant

        with platform_db_manager.get_platform_session() as db_session:
            tenant = (
                db_session.query(Tenant)
                .filter(Tenant.id == admin_session.tenant_id)
                .first()
            )
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            updated_fields = []

            if body.join_approval_required is not None:
                tenant.join_approval_required = body.join_approval_required
                updated_fields.append("join_approval_required")

            if body.description is not None:
                tenant.description = body.description
                updated_fields.append("description")

            if body.organization is not None:
                tenant.organization = body.organization
                updated_fields.append("organization")

            if body.email_response_format is not None:
                valid_formats = {"html", "markdown", "text", ""}
                fmt = body.email_response_format.strip().lower()
                if fmt not in valid_formats:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid email_response_format: must be html, markdown, text, or empty",
                    )
                tenant.email_response_format = fmt if fmt else None
                updated_fields.append("email_response_format")

            if updated_fields:
                tenant.updated_at = datetime.utcnow()

            logger.info(
                f"Tenant settings updated for '{admin_session.tenant_slug}': "
                f"{', '.join(updated_fields) or 'no changes'}"
            )

            return AdminActionResponse(
                success=True,
                message="Settings updated successfully.",
                details={
                    "slug": tenant.slug,
                    "email_address": tenant.email_address or "",
                    "description": tenant.description or "",
                    "organization": tenant.organization or "",
                },
            )

    @router.get("/join-requests")
    def list_join_requests(admin_session=Depends(require_admin)):
        """List pending join requests for the current tenant."""

        from src.platform.models import JoinRequest, JoinRequestStatus

        with platform_db_manager.get_platform_session() as db_session:
            requests = (
                db_session.query(JoinRequest)
                .filter(
                    JoinRequest.tenant_id == admin_session.tenant_id,
                    JoinRequest.status == JoinRequestStatus.PENDING,
                )
                .order_by(JoinRequest.created_at.desc())
                .all()
            )

            return [r.to_dict() for r in requests]

    @router.post("/join-requests/{request_id}/approve")
    def approve_join_request(
        request_id: int,
        background_tasks: BackgroundTasks,
        admin_session=Depends(require_admin),
    ):
        """
        Approve a join request, creating a TenantUser.

        Args:
            request_id: Join request ID to approve.
        """

        from src.platform.models import (
            JoinRequest,
            JoinRequestStatus,
            TenantUser,
            TenantUserRole,
        )

        with platform_db_manager.get_platform_session() as db_session:
            join_request = (
                db_session.query(JoinRequest)
                .filter(
                    JoinRequest.id == request_id,
                    JoinRequest.tenant_id == admin_session.tenant_id,
                )
                .first()
            )

            if not join_request:
                raise HTTPException(status_code=404, detail="Join request not found")

            if join_request.status != JoinRequestStatus.PENDING:
                return JoinRequestActionResponse(
                    success=False,
                    message=f"Request already {join_request.status.value}.",
                )

            # Create TenantUser
            user = TenantUser(
                email=join_request.email,
                tenant_id=admin_session.tenant_id,
                role=TenantUserRole.QUERIER,
            )
            db_session.add(user)

            # Update join request
            join_request.status = JoinRequestStatus.APPROVED
            join_request.resolved_at = datetime.utcnow()
            join_request.resolved_by = admin_session.email

            approved_email = join_request.email

            logger.info(
                f"Join request #{request_id} approved by "
                f"{admin_session.email} for {approved_email}"
            )

            # Send welcome email to the approved user
            if email_sender:
                from src.email.email_sender import (
                    fetch_tenant_welcome_params,
                    send_welcome_email,
                )

                params = fetch_tenant_welcome_params(
                    admin_session.tenant_id, db_session=db_session
                )

                background_tasks.add_task(
                    send_welcome_email,
                    sender_instance=email_sender,
                    to_email=approved_email,
                    role="querier",
                    **params,
                )

            return JoinRequestActionResponse(
                success=True,
                message=f"Approved {approved_email}.",
            )

    @router.post("/join-requests/{request_id}/reject")
    def reject_join_request(
        request_id: int,
        admin_session=Depends(require_admin),
    ):
        """
        Reject a join request.

        Args:
            request_id: Join request ID to reject.
        """

        from src.platform.models import JoinRequest, JoinRequestStatus

        with platform_db_manager.get_platform_session() as db_session:
            join_request = (
                db_session.query(JoinRequest)
                .filter(
                    JoinRequest.id == request_id,
                    JoinRequest.tenant_id == admin_session.tenant_id,
                )
                .first()
            )

            if not join_request:
                raise HTTPException(status_code=404, detail="Join request not found")

            if join_request.status != JoinRequestStatus.PENDING:
                return JoinRequestActionResponse(
                    success=False,
                    message=f"Request already {join_request.status.value}.",
                )

            join_request.status = JoinRequestStatus.REJECTED
            join_request.resolved_at = datetime.utcnow()
            join_request.resolved_by = admin_session.email

            logger.info(
                f"Join request #{request_id} rejected by "
                f"{admin_session.email} for {join_request.email}"
            )

            return JoinRequestActionResponse(
                success=True,
                message=f"Rejected {join_request.email}.",
            )

    @router.get("/invite/qr")
    def get_invite_qr(admin_session=Depends(require_admin)):
        """
        Generate a QR code PNG for the tenant invite link.

        Returns a PNG image containing a QR code that points to
        the landing page with the invite code pre-filled.
        """

        from src.platform.models import Tenant

        with platform_db_manager.get_platform_session() as db_session:
            tenant = (
                db_session.query(Tenant)
                .filter(Tenant.id == admin_session.tenant_id)
                .first()
            )
            if not tenant or not tenant.invite_code:
                raise HTTPException(status_code=404, detail="Invite code not found")

            try:
                import qrcode
            except ImportError:
                raise HTTPException(
                    status_code=501,
                    detail="QR code generation not available. "
                    "Install qrcode[pil] package.",
                )

            # Build invite URL
            base_url = settings.platform_base_url or "https://berengar.io"
            invite_url = (
                f"{base_url}/static/onboarding.html"
                f"?mode=join&code={tenant.invite_code}"
            )

            # Generate QR code with minimal complexity for short URLs
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=8,
                border=2,
            )
            qr.add_data(invite_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            # Write to bytes buffer
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            return StreamingResponse(
                buf,
                media_type="image/png",
                headers={
                    "Content-Disposition": (
                        f"inline; filename={tenant.slug}-invite-qr.png"
                    )
                },
            )

    return router
