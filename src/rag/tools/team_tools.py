"""
Team management tools.

Provides LLM-callable functions to add/remove team members.
Uses TenantUser records in the platform database.
"""

import logging
from typing import Any, Dict

from .base import ParameterType, Tool, ToolParameter, register_tool
from .context import get_tenant_id, get_user_email, validate_admin_access

logger = logging.getLogger(__name__)

# Lazy-initialized platform DB engine
_platform_engine = None


def _get_platform_session():
    """
    Get a platform DB session (lazy engine creation).

    Returns:
        SQLAlchemy Session instance for the platform database.
    """
    global _platform_engine
    if _platform_engine is None:
        from sqlalchemy import create_engine

        from src.config import settings

        _platform_engine = create_engine(settings.get_platform_database_url())
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=_platform_engine)()


def add_team_member(email: str, role: str = "querier") -> Dict[str, Any]:
    """
    Add a user to the current tenant's team (multi-tenant mode only).

    ADMIN ONLY. Creates a TenantUser record in the platform database.
    Sends a welcome email to the new user on success.

    Args:
        email: Email address of the user to add.
        role: Role to assign — "querier" (default) or "teacher".

    Returns:
        Dictionary with success status and message.
    """
    try:
        validate_admin_access()

        email = email.strip().lower()
        if not email:
            raise ValueError("Email address cannot be empty")

        # Validate role
        role = role.strip().lower()
        if role == "admin":
            return {
                "success": False,
                "message": (
                    "Cannot assign the admin role via this tool for security reasons. "
                    "Use the platform admin panel to manage administrator roles."
                ),
            }
        if role not in ("querier", "teacher"):
            return {
                "success": False,
                "message": f"Invalid role '{role}'. Must be 'querier' or 'teacher'.",
            }

        tenant_id = get_tenant_id()
        if tenant_id is None:
            return {
                "success": False,
                "message": "No tenant context available. Cannot add team member.",
            }

        from src.platform.models import TenantUser, TenantUserRole

        role_enum = (
            TenantUserRole.TEACHER if role == "teacher" else TenantUserRole.QUERIER
        )

        session = _get_platform_session()
        try:
            existing = (
                session.query(TenantUser)
                .filter_by(email=email, tenant_id=tenant_id)
                .first()
            )
            if existing:
                return {
                    "success": True,
                    "message": f"{email} is already a member of this team (role: {existing.role.value}). No changes were made.",
                }

            user = TenantUser(email=email, tenant_id=tenant_id, role=role_enum)
            session.add(user)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        admin_email = get_user_email()
        logger.info(
            f"MT: Admin {admin_email} added {email} as {role} to tenant {tenant_id}"
        )

        # Send welcome email with tenant-specific values (non-critical)
        try:
            from src.email.email_sender import (
                EmailSender,
                fetch_tenant_welcome_params,
                send_welcome_email,
            )

            sender = EmailSender()
            params = fetch_tenant_welcome_params(tenant_id)

            send_welcome_email(
                sender_instance=sender,
                to_email=email,
                role=role,
                **params,
            )
        except Exception as e:
            logger.warning(f"Failed to send welcome email to {email}: {e}")

        return {
            "success": True,
            "message": f"Successfully added {email} as a {role}. They will receive a welcome email with instructions.",
        }

    except PermissionError as e:
        return {"success": False, "message": f"Permission denied: {str(e)}"}
    except Exception as e:
        logger.error(f"Error adding team member: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}


def remove_team_member(email: str) -> Dict[str, Any]:
    """
    Remove a user from the current tenant's team (multi-tenant mode only).

    ADMIN ONLY. Deletes the TenantUser record from the platform database.

    Args:
        email: Email address of the user to remove.

    Returns:
        Dictionary with success status and message.
    """
    try:
        validate_admin_access()

        email = email.strip().lower()
        if not email:
            raise ValueError("Email address cannot be empty")

        tenant_id = get_tenant_id()
        if tenant_id is None:
            return {
                "success": False,
                "message": "No tenant context available. Cannot remove team member.",
            }

        from src.platform.models import TenantUser

        session = _get_platform_session()
        try:
            user = (
                session.query(TenantUser)
                .filter_by(email=email, tenant_id=tenant_id)
                .first()
            )
            if not user:
                return {
                    "success": False,
                    "message": f"{email} is not a member of this team.",
                }

            session.delete(user)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        admin_email = get_user_email()
        logger.info(f"MT: Admin {admin_email} removed {email} from tenant {tenant_id}")

        return {
            "success": True,
            "message": f"Successfully removed {email} from the team.",
        }

    except PermissionError as e:
        return {"success": False, "message": f"Permission denied: {str(e)}"}
    except Exception as e:
        logger.error(f"Error removing team member: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}


# Tool definitions
add_team_member_tool = Tool(
    name="add_team_member",
    description=(
        "Add a user to the team. Creates a team membership with "
        "the specified role. ADMIN ONLY. Use 'querier' for users who should only ask "
        "questions, or 'teacher' for users who can also add content to the knowledge base."
    ),
    parameters=[
        ToolParameter(
            name="email",
            type=ParameterType.STRING,
            description="Email address of the user to add",
            required=True,
        ),
        ToolParameter(
            name="role",
            type=ParameterType.STRING,
            description="Role to assign: 'querier' (can ask questions) or 'teacher' (can ask questions and add content)",
            required=False,
            enum=["querier", "teacher"],
        ),
    ],
    function=add_team_member,
    returns_attachment=False,
)

remove_team_member_tool = Tool(
    name="remove_team_member",
    description=(
        "Remove a user from the team. Revokes their access entirely. " "ADMIN ONLY."
    ),
    parameters=[
        ToolParameter(
            name="email",
            type=ParameterType.STRING,
            description="Email address of the user to remove",
            required=True,
        ),
    ],
    function=remove_team_member,
    returns_attachment=False,
)

# Register tools
register_tool(add_team_member_tool)
register_tool(remove_team_member_tool)
