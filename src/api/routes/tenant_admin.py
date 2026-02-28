"""
Tenant administration routes for multi-tenant mode.

Handles invite code management, join request approval/rejection,
and tenant-level settings. All endpoints require admin privileges.
"""

import io
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
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
):
    """
    Create tenant admin router with dependency injection.

    Args:
        platform_db_manager: TenantDBManager for platform DB access.
        require_admin: FastAPI dependency that checks admin status.
        session_manager: Session management instance.
        get_session_id: Function to extract session ID from request.
        settings: Application settings.

    Returns:
        Configured APIRouter instance.
    """
    router = APIRouter(
        prefix="/api/admin/tenant",
        tags=["tenant-admin"],
    )

    @router.get("/invite")
    async def get_invite_info(session=None):
        """Get invite code and join settings for the current tenant."""
        admin_session = await require_admin(session)

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
    async def regenerate_invite_code(session=None):
        """Generate a new invite code, invalidating the old one."""
        admin_session = await require_admin(session)

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
    async def update_tenant_settings(
        body: TenantSettingsRequest,
        session=None,
    ):
        """Update tenant join settings."""
        admin_session = await require_admin(session)

        from src.platform.models import Tenant

        with platform_db_manager.get_platform_session() as db_session:
            tenant = (
                db_session.query(Tenant)
                .filter(Tenant.id == admin_session.tenant_id)
                .first()
            )
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            tenant.join_approval_required = body.join_approval_required
            tenant.updated_at = datetime.utcnow()

            logger.info(
                f"Tenant settings updated for '{admin_session.tenant_slug}': "
                f"join_approval_required={body.join_approval_required}"
            )

            return AdminActionResponse(
                success=True,
                message="Settings updated successfully.",
            )

    @router.get("/join-requests")
    async def list_join_requests(session=None):
        """List pending join requests for the current tenant."""
        admin_session = await require_admin(session)

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
    async def approve_join_request(request_id: int, session=None):
        """
        Approve a join request, creating a TenantUser.

        Args:
            request_id: Join request ID to approve.
        """
        admin_session = await require_admin(session)

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

            logger.info(
                f"Join request #{request_id} approved by "
                f"{admin_session.email} for {join_request.email}"
            )

            return JoinRequestActionResponse(
                success=True,
                message=f"Approved {join_request.email}.",
            )

    @router.post("/join-requests/{request_id}/reject")
    async def reject_join_request(request_id: int, session=None):
        """
        Reject a join request.

        Args:
            request_id: Join request ID to reject.
        """
        admin_session = await require_admin(session)

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
    async def get_invite_qr(session=None):
        """
        Generate a QR code PNG for the tenant invite link.

        Returns a PNG image containing a QR code that points to
        the landing page with the invite code pre-filled.
        """
        admin_session = await require_admin(session)

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

            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
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
