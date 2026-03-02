"""
Admin email commands for managing team members via email.

Allows admins to add users by emailing the bot naturally, e.g.:
    "Hi Berengario, please add Marcus <marcus@example.com> to the team"

Detection, parsing, and execution are separated for testability.
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Trigger verbs that signal an "add user" intent
_TRIGGER_VERBS = r"(?:add|invite|enroll|register|include|give\s+access|grant\s+access)"

# Email pattern (bare or angle-bracketed)
_EMAIL_RE = r"<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?"

# Pattern: trigger verb → up to 60 chars → email address
_CMD_PATTERN = re.compile(
    rf"{_TRIGGER_VERBS}\s.{{0,60}}?{_EMAIL_RE}",
    re.IGNORECASE | re.DOTALL,
)

# Alternate pattern: email first, then role/context words
_CMD_PATTERN_ALT = re.compile(
    rf"{_EMAIL_RE}\s+(?:as\s+(?:a\s+)?(?:teacher|querier|member)|to\s+the\s+team)",
    re.IGNORECASE,
)


@dataclass
class AddUserCommand:
    """Parsed result of an add-user email command."""

    email: str
    role: str  # "querier" or "teacher"
    error: Optional[str] = None  # Set if role is invalid (e.g. "admin")


def detect_add_user_command(subject: str, body: str) -> bool:
    """
    Detect whether an email is an "add user" command.

    Only called when sender is already confirmed admin, so
    false-positive risk on normal queries is low.

    Args:
        subject: Email subject line.
        body: Email body text.

    Returns:
        True if the email looks like an add-user command.
    """
    text = f"{subject} {body}"
    return bool(_CMD_PATTERN.search(text) or _CMD_PATTERN_ALT.search(text))


def parse_add_user_command(subject: str, body: str) -> Optional[AddUserCommand]:
    """
    Parse an add-user command from email subject + body.

    Args:
        subject: Email subject line.
        body: Email body text.

    Returns:
        AddUserCommand with extracted email and role, or None if
        no valid command found.
    """
    text = f"{subject} {body}"

    # Try primary pattern first, then alternate
    match = _CMD_PATTERN.search(text)
    if not match:
        match = _CMD_PATTERN_ALT.search(text)
    if not match:
        return None

    email = match.group(1).lower().strip()

    # Determine role from surrounding context
    # Look in a window around the email address for role keywords
    match_start = max(0, match.start() - 20)
    match_end = min(len(text), match.end() + 60)
    context = text[match_start:match_end].lower()

    if "admin" in context:
        return AddUserCommand(
            email=email,
            role="querier",
            error="admin_role_requested",
        )

    if "teacher" in context:
        return AddUserCommand(email=email, role="teacher")

    # Default role
    return AddUserCommand(email=email, role="querier")


def execute_add_user_st(
    command: AddUserCommand,
    whitelist_manager,
    reload_callback: Callable[[], None],
) -> tuple[bool, str]:
    """
    Execute add-user command in single-tenant mode.

    Uses WhitelistManager to add entries to whitelist files,
    then calls reload_callback to refresh in-memory validators.

    Args:
        command: Parsed add-user command.
        whitelist_manager: WhitelistManager instance for file ops.
        reload_callback: Callable to reload whitelist validators.

    Returns:
        Tuple of (success, message).
    """
    email = command.email
    role = command.role

    try:
        # Always add to queriers (all roles can query)
        added_querier = whitelist_manager.add_entry("queriers", email)

        added_teacher = False
        if role == "teacher":
            added_teacher = whitelist_manager.add_entry("teachers", email)

        # Reload validators to pick up file changes
        reload_callback()

        if not added_querier and not added_teacher:
            return (True, f"{email} is already a member. No changes were made.")

        role_label = "teacher" if role == "teacher" else "querier"
        return (
            True,
            f"Done! I've added {email} as a {role_label}. "
            f"They'll receive a welcome email with instructions.",
        )

    except Exception as e:
        logger.error(f"Failed to add user {email} via ST command: {e}")
        return (False, f"Sorry, I couldn't add {email}: {str(e)}")


def execute_add_user_mt(
    command: AddUserCommand,
    tenant_id: str,
    tenant_slug: str,
    db_manager,
) -> tuple[bool, str]:
    """
    Execute add-user command in multi-tenant mode.

    Creates a TenantUser record in the platform database.

    Args:
        command: Parsed add-user command.
        tenant_id: Target tenant ID.
        tenant_slug: Target tenant slug (for logging).
        db_manager: TenantDBManager with get_platform_session().

    Returns:
        Tuple of (success, message).
    """
    from src.platform.models import TenantUser, TenantUserRole

    email = command.email
    role_enum = (
        TenantUserRole.TEACHER if command.role == "teacher" else TenantUserRole.QUERIER
    )

    try:
        with db_manager.get_platform_session() as session:
            # Check for existing user in this tenant
            existing = (
                session.query(TenantUser)
                .filter_by(email=email, tenant_id=tenant_id)
                .first()
            )
            if existing:
                return (
                    True,
                    f"{email} is already a member of this team. "
                    f"No changes were made.",
                )

            user = TenantUser(
                email=email,
                tenant_id=tenant_id,
                role=role_enum,
            )
            session.add(user)
            session.commit()

        role_label = command.role
        logger.info(
            f"MT: Added {email} as {role_label} to tenant '{tenant_slug}' via email command"
        )
        return (
            True,
            f"Done! I've added {email} as a {role_label}. "
            f"They'll receive a welcome email with instructions.",
        )

    except Exception as e:
        logger.error(f"MT: Failed to add user {email} to tenant '{tenant_slug}': {e}")
        return (False, f"Sorry, I couldn't add {email}: {str(e)}")
