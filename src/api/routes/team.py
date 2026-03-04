"""
Team management routes for multi-tenant mode.

CRUD operations on TenantUser records, scoped to the admin's active tenant.
Only available when MULTI_TENANT=true.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from src.api.models import AdminActionResponse, TeamMemberRequest, TeamMemberResponse

logger = logging.getLogger(__name__)


def create_team_router(
    platform_db_manager,
    require_admin,
    email_sender=None,
):
    """
    Create team management router with dependency injection.

    Args:
        platform_db_manager: TenantDBManager for platform DB access.
        require_admin: Admin authentication dependency.
        email_sender: EmailSender instance for welcome emails (optional).

    Returns:
        Configured APIRouter instance.
    """
    router = APIRouter(prefix="/api/admin/team", tags=["team"])

    @router.get("", response_model=list[TeamMemberResponse])
    def list_team_members(
        session=Depends(require_admin),
    ):
        """
        List all team members for the admin's active tenant.

        Args:
            session: Admin session (injected by dependency).

        Returns:
            List of TeamMemberResponse objects.
        """
        if not session.tenant_id:
            raise HTTPException(status_code=400, detail="No active tenant selected.")

        from src.platform.models import TenantUser

        with platform_db_manager.get_platform_session() as db_session:
            users = (
                db_session.query(TenantUser)
                .filter(TenantUser.tenant_id == session.tenant_id)
                .order_by(TenantUser.created_at)
                .all()
            )

            return [
                TeamMemberResponse(
                    id=u.id,
                    email=u.email,
                    role=u.role.value if hasattr(u.role, "value") else u.role,
                    tenant_id=u.tenant_id,
                    created_at=u.created_at.isoformat() if u.created_at else "",
                )
                for u in users
            ]

    @router.post("", response_model=AdminActionResponse)
    def add_team_member(
        request: TeamMemberRequest,
        background_tasks: BackgroundTasks,
        session=Depends(require_admin),
    ):
        """
        Add a user to the admin's active tenant with a role.

        Args:
            request: TeamMemberRequest with email and role.
            session: Admin session (injected by dependency).

        Returns:
            AdminActionResponse with success status.
        """
        if not session.tenant_id:
            raise HTTPException(status_code=400, detail="No active tenant selected.")

        if not request.email:
            raise HTTPException(status_code=400, detail="Email is required.")

        from src.platform.models import TenantUser, TenantUserRole

        # Validate role
        try:
            role = TenantUserRole(request.role)
        except ValueError:
            valid = ", ".join(r.value for r in TenantUserRole)
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role '{request.role}'. Valid roles: {valid}",
            )

        email = request.email.lower()

        with platform_db_manager.get_platform_session() as db_session:
            # Check if user already exists in this tenant
            existing = (
                db_session.query(TenantUser)
                .filter(
                    TenantUser.email == email,
                    TenantUser.tenant_id == session.tenant_id,
                )
                .first()
            )

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"User '{email}' is already a member of this tenant.",
                )

            user = TenantUser(
                email=email,
                tenant_id=session.tenant_id,
                role=role,
                created_at=datetime.utcnow(),
            )
            db_session.add(user)
            db_session.commit()

            logger.info(
                f"Admin {session.email} added {email} as {role.value} "
                f"to tenant {session.tenant_slug}"
            )

        # Send welcome email in background
        if email_sender:
            from src.email.email_sender import (
                fetch_tenant_welcome_params,
                send_welcome_email,
            )

            params = fetch_tenant_welcome_params(session.tenant_id)

            background_tasks.add_task(
                send_welcome_email,
                sender_instance=email_sender,
                to_email=email,
                role=role.value,
                **params,
            )

        return AdminActionResponse(
            success=True,
            message=f"Added {email} as {role.value}",
            details={"email": email, "role": role.value},
        )

    @router.put("/{user_id}", response_model=AdminActionResponse)
    def update_team_member(
        user_id: int,
        request: TeamMemberRequest,
        session=Depends(require_admin),
    ):
        """
        Update a team member's role.

        Args:
            user_id: TenantUser ID to update.
            request: TeamMemberRequest with new role.
            session: Admin session (injected by dependency).

        Returns:
            AdminActionResponse with success status.
        """
        if not session.tenant_id:
            raise HTTPException(status_code=400, detail="No active tenant selected.")

        from src.platform.models import TenantUser, TenantUserRole

        try:
            role = TenantUserRole(request.role)
        except ValueError:
            valid = ", ".join(r.value for r in TenantUserRole)
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role '{request.role}'. Valid roles: {valid}",
            )

        with platform_db_manager.get_platform_session() as db_session:
            user = (
                db_session.query(TenantUser)
                .filter(
                    TenantUser.id == user_id,
                    TenantUser.tenant_id == session.tenant_id,
                )
                .first()
            )

            if not user:
                raise HTTPException(status_code=404, detail="Team member not found.")

            old_role = user.role.value if hasattr(user.role, "value") else user.role
            email = user.email
            user.role = role
            db_session.commit()

            logger.info(
                f"Admin {session.email} changed {email} role "
                f"from {old_role} to {role.value} in tenant {session.tenant_slug}"
            )

        return AdminActionResponse(
            success=True,
            message=f"Updated {email} role to {role.value}",
            details={"email": email, "old_role": old_role, "new_role": role.value},
        )

    @router.delete("/{user_id}", response_model=AdminActionResponse)
    def remove_team_member(
        user_id: int,
        session=Depends(require_admin),
    ):
        """
        Remove a team member from the tenant.

        Args:
            user_id: TenantUser ID to remove.
            session: Admin session (injected by dependency).

        Returns:
            AdminActionResponse with success status.
        """
        if not session.tenant_id:
            raise HTTPException(status_code=400, detail="No active tenant selected.")

        from src.platform.models import TenantUser

        with platform_db_manager.get_platform_session() as db_session:
            user = (
                db_session.query(TenantUser)
                .filter(
                    TenantUser.id == user_id,
                    TenantUser.tenant_id == session.tenant_id,
                )
                .first()
            )

            if not user:
                raise HTTPException(status_code=404, detail="Team member not found.")

            # Don't allow removing yourself
            if user.email == session.email:
                raise HTTPException(
                    status_code=400,
                    detail="You cannot remove yourself from the team.",
                )

            email = user.email
            db_session.delete(user)
            db_session.commit()

            logger.info(
                f"Admin {session.email} removed {email} "
                f"from tenant {session.tenant_slug}"
            )

        return AdminActionResponse(
            success=True,
            message=f"Removed {email} from team",
            details={"email": email},
        )

    return router
