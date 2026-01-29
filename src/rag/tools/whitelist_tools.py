"""
Whitelist management tools for adding/removing users from access lists.

Provides functions to manage teach and query whitelists, restricted to admin users.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from src.config import settings
from src.email.email_sender import EmailSender

from .base import ParameterType, Tool, ToolParameter, register_tool
from .context import get_tool_context, is_email_request, validate_admin_access
from .pending_actions import get_pending_action_manager

logger = logging.getLogger(__name__)

# Global email sender instance
_email_sender = None


def _get_email_sender() -> EmailSender:
    """Get or create email sender instance."""
    global _email_sender
    if _email_sender is None:
        _email_sender = EmailSender()
    return _email_sender


def _add_to_whitelist_file(filepath: Path, email: str) -> None:
    """
    Add an email to a whitelist file.

    Args:
        filepath: Path to the whitelist file
        email: Email address or domain to add
    """
    # Read existing entries
    existing = set()
    if filepath.exists():
        with open(filepath, "r") as f:
            existing = {
                line.strip() for line in f if line.strip() and not line.startswith("#")
            }

    # Check if already exists
    if email in existing:
        logger.info(f"Email {email} already in whitelist {filepath}")
        return

    # Add new entry
    with open(filepath, "a") as f:
        f.write(f"{email}\n")
    logger.info(f"Added {email} to whitelist {filepath}")


def _remove_from_whitelist_file(filepath: Path, email: str) -> bool:
    """
    Remove an email from a whitelist file.

    Args:
        filepath: Path to the whitelist file
        email: Email address or domain to remove

    Returns:
        True if removed, False if not found
    """
    if not filepath.exists():
        return False

    # Read all lines
    with open(filepath, "r") as f:
        lines = f.readlines()

    # Filter out the email to remove
    new_lines = []
    found = False
    for line in lines:
        stripped = line.strip()
        if stripped == email:
            found = True
            logger.info(f"Removing {email} from whitelist {filepath}")
        else:
            new_lines.append(line)

    if found:
        # Write back filtered lines
        with open(filepath, "w") as f:
            f.writelines(new_lines)
        return True
    else:
        logger.info(f"Email {email} not found in whitelist {filepath}")
        return False


def add_to_teach_whitelist(email: str) -> Dict[str, Any]:
    """
    Add a user to the teach whitelist (allows adding content to knowledge base).

    ADMIN ONLY: This function can only be called by administrators.
    EMAIL REQUESTS: Require confirmation via reply to prevent spoofing.

    Args:
        email: Email address or domain pattern (e.g., user@example.com or @example.com)

    Returns:
        Dictionary with success status and message
    """
    try:
        validate_admin_access()

        email = email.strip().lower()
        if not email:
            raise ValueError("Email address cannot be empty")

        context = get_tool_context()
        admin_email = context.get("user_email", "unknown")
        is_email_req = is_email_request()

        # Email requests require confirmation to prevent spoofing
        if is_email_req:
            pending_mgr = get_pending_action_manager()
            action = pending_mgr.create_pending_action(
                action_type="add_teach",
                email_to_modify=email,
                requested_by=admin_email,
            )

            logger.info(
                f"Created pending action {action.action_id} for adding {email} to teach whitelist "
                f"(requested by {admin_email})"
            )

            # Send confirmation email to admin
            try:
                email_sender = _get_email_sender()
                email_sender.send_reply(
                    to_address=admin_email,
                    subject=f"Confirm: Add '{email}' to Teach Whitelist",
                    body_text=(
                        f"CONFIRMATION REQUIRED\n\n"
                        f"You requested to add '{email}' to the teach whitelist.\n\n"
                        f"To confirm this action, simply reply to this email. "
                        f"You don't need to add anything in your reply.\n\n"
                        f"Confirmation token: {action.action_id}\n\n"
                        f"This confirmation is required to prevent email spoofing attacks. "
                        f"The confirmation will expire in 30 minutes.\n\n"
                        f"If you did not make this request, you can safely ignore this email."
                    ),
                    body_html=None,
                )
                logger.info(
                    f"Sent confirmation email to {admin_email} for action {action.action_id}"
                )
            except Exception as e:
                logger.error(f"Failed to send confirmation email: {e}", exc_info=True)

            return {
                "success": True,
                "pending": True,
                "action_id": action.action_id,
                "email_sent": True,  # Flag to indicate confirmation email was already sent
                "message": (
                    f"A confirmation email has been sent to {admin_email}. "
                    f"Please reply to that email within 30 minutes to confirm adding '{email}' to the teach whitelist."
                ),
            }

        # Web requests execute immediately (already authenticated via OTP)
        whitelist_file = Path(settings.email_teach_whitelist_file)
        whitelist_file.parent.mkdir(parents=True, exist_ok=True)

        _add_to_whitelist_file(whitelist_file, email)

        logger.info(f"Admin {admin_email} added {email} to teach whitelist")

        return {
            "success": True,
            "message": f"Successfully added '{email}' to the teach whitelist. They can now add content to the knowledge base.",
        }

    except PermissionError as e:
        return {
            "success": False,
            "message": f"Permission denied: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Error adding to teach whitelist: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}",
        }


def remove_from_teach_whitelist(email: str) -> Dict[str, Any]:
    """
    Remove a user from the teach whitelist.

    ADMIN ONLY: This function can only be called by administrators.
    EMAIL REQUESTS: Require confirmation via reply to prevent spoofing.

    Args:
        email: Email address or domain pattern to remove

    Returns:
        Dictionary with success status and message
    """
    try:
        validate_admin_access()

        email = email.strip().lower()
        if not email:
            raise ValueError("Email address cannot be empty")

        context = get_tool_context()
        admin_email = context.get("user_email", "unknown")
        is_email_req = is_email_request()

        # Email requests require confirmation to prevent spoofing
        if is_email_req:
            pending_mgr = get_pending_action_manager()
            action = pending_mgr.create_pending_action(
                action_type="remove_teach",
                email_to_modify=email,
                requested_by=admin_email,
            )

            logger.info(
                f"Created pending action {action.action_id} for removing {email} from teach whitelist "
                f"(requested by {admin_email})"
            )

            # Send confirmation email to admin
            try:
                email_sender = _get_email_sender()
                email_sender.send_reply(
                    to_address=admin_email,
                    subject=f"Confirm: Remove '{email}' from Teach Whitelist",
                    body_text=(
                        f"CONFIRMATION REQUIRED\n\n"
                        f"You requested to remove '{email}' from the teach whitelist.\n\n"
                        f"To confirm this action, simply reply to this email. "
                        f"You don't need to add anything in your reply.\n\n"
                        f"Confirmation token: {action.action_id}\n\n"
                        f"This confirmation is required to prevent email spoofing attacks. "
                        f"The confirmation will expire in 30 minutes.\n\n"
                        f"If you did not make this request, you can safely ignore this email."
                    ),
                    body_html=None,
                )
                logger.info(
                    f"Sent confirmation email to {admin_email} for action {action.action_id}"
                )
            except Exception as e:
                logger.error(f"Failed to send confirmation email: {e}", exc_info=True)

            return {
                "success": True,
                "pending": True,
                "action_id": action.action_id,
                "email_sent": True,  # Flag to indicate confirmation email was already sent
                "message": (
                    f"A confirmation email has been sent to {admin_email}. "
                    f"Please reply to that email within 30 minutes to confirm removing '{email}' from the teach whitelist."
                ),
            }

        # Web requests execute immediately (already authenticated via OTP)
        whitelist_file = Path(settings.email_teach_whitelist_file)
        removed = _remove_from_whitelist_file(whitelist_file, email)

        if removed:
            logger.info(f"Admin {admin_email} removed {email} from teach whitelist")
            return {
                "success": True,
                "message": f"Successfully removed '{email}' from the teach whitelist.",
            }
        else:
            return {
                "success": False,
                "message": f"'{email}' was not found in the teach whitelist.",
            }

    except PermissionError as e:
        return {
            "success": False,
            "message": f"Permission denied: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Error removing from teach whitelist: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}",
        }


def add_to_query_whitelist(email: str) -> Dict[str, Any]:
    """
    Add a user to the query whitelist (allows asking questions).

    ADMIN ONLY: This function can only be called by administrators.
    EMAIL REQUESTS: Require confirmation via reply to prevent spoofing.

    Args:
        email: Email address or domain pattern (e.g., user@example.com or @example.com)

    Returns:
        Dictionary with success status and message
    """
    try:
        validate_admin_access()

        email = email.strip().lower()
        if not email:
            raise ValueError("Email address cannot be empty")

        context = get_tool_context()
        admin_email = context.get("user_email", "unknown")
        is_email_req = is_email_request()

        # Email requests require confirmation to prevent spoofing
        if is_email_req:
            pending_mgr = get_pending_action_manager()
            action = pending_mgr.create_pending_action(
                action_type="add_query",
                email_to_modify=email,
                requested_by=admin_email,
            )

            logger.info(
                f"Created pending action {action.action_id} for adding {email} to query whitelist "
                f"(requested by {admin_email})"
            )

            # Send confirmation email to admin
            try:
                email_sender = _get_email_sender()
                email_sender.send_reply(
                    to_address=admin_email,
                    subject=f"Confirm: Add '{email}' to Query Whitelist",
                    body_text=(
                        f"CONFIRMATION REQUIRED\n\n"
                        f"You requested to add '{email}' to the query whitelist.\n\n"
                        f"To confirm this action, simply reply to this email. "
                        f"You don't need to add anything in your reply.\n\n"
                        f"Confirmation token: {action.action_id}\n\n"
                        f"This confirmation is required to prevent email spoofing attacks. "
                        f"The confirmation will expire in 30 minutes.\n\n"
                        f"If you did not make this request, you can safely ignore this email."
                    ),
                    body_html=None,
                )
                logger.info(
                    f"Sent confirmation email to {admin_email} for action {action.action_id}"
                )
            except Exception as e:
                logger.error(f"Failed to send confirmation email: {e}", exc_info=True)

            return {
                "success": True,
                "pending": True,
                "action_id": action.action_id,
                "email_sent": True,  # Flag to indicate confirmation email was already sent
                "message": (
                    f"A confirmation email has been sent to {admin_email}. "
                    f"Please reply to that email within 30 minutes to confirm adding '{email}' to the query whitelist."
                ),
            }

        # Web requests execute immediately (already authenticated via OTP)
        whitelist_file = Path(settings.email_query_whitelist_file)
        whitelist_file.parent.mkdir(parents=True, exist_ok=True)

        _add_to_whitelist_file(whitelist_file, email)

        logger.info(f"Admin {admin_email} added {email} to query whitelist")

        return {
            "success": True,
            "message": f"Successfully added '{email}' to the query whitelist. They can now ask questions.",
        }

    except PermissionError as e:
        return {
            "success": False,
            "message": f"Permission denied: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Error adding to query whitelist: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}",
        }


def remove_from_query_whitelist(email: str) -> Dict[str, Any]:
    """
    Remove a user from the query whitelist.

    ADMIN ONLY: This function can only be called by administrators.
    EMAIL REQUESTS: Require confirmation via reply to prevent spoofing.

    Args:
        email: Email address or domain pattern to remove

    Returns:
        Dictionary with success status and message
    """
    try:
        validate_admin_access()

        email = email.strip().lower()
        if not email:
            raise ValueError("Email address cannot be empty")

        context = get_tool_context()
        admin_email = context.get("user_email", "unknown")
        is_email_req = is_email_request()

        # Email requests require confirmation to prevent spoofing
        if is_email_req:
            pending_mgr = get_pending_action_manager()
            action = pending_mgr.create_pending_action(
                action_type="remove_query",
                email_to_modify=email,
                requested_by=admin_email,
            )

            logger.info(
                f"Created pending action {action.action_id} for removing {email} from query whitelist "
                f"(requested by {admin_email})"
            )

            # Send confirmation email to admin
            try:
                email_sender = _get_email_sender()
                email_sender.send_reply(
                    to_address=admin_email,
                    subject=f"Confirm: Remove '{email}' from Query Whitelist",
                    body_text=(
                        f"CONFIRMATION REQUIRED\n\n"
                        f"You requested to remove '{email}' from the query whitelist.\n\n"
                        f"To confirm this action, simply reply to this email. "
                        f"You don't need to add anything in your reply.\n\n"
                        f"Confirmation token: {action.action_id}\n\n"
                        f"This confirmation is required to prevent email spoofing attacks. "
                        f"The confirmation will expire in 30 minutes.\n\n"
                        f"If you did not make this request, you can safely ignore this email."
                    ),
                    body_html=None,
                )
                logger.info(
                    f"Sent confirmation email to {admin_email} for action {action.action_id}"
                )
            except Exception as e:
                logger.error(f"Failed to send confirmation email: {e}", exc_info=True)

            return {
                "success": True,
                "pending": True,
                "action_id": action.action_id,
                "email_sent": True,  # Flag to indicate confirmation email was already sent
                "message": (
                    f"A confirmation email has been sent to {admin_email}. "
                    f"Please reply to that email within 30 minutes to confirm removing '{email}' from the query whitelist."
                ),
            }

        # Web requests execute immediately (already authenticated via OTP)
        whitelist_file = Path(settings.email_query_whitelist_file)
        removed = _remove_from_whitelist_file(whitelist_file, email)

        if removed:
            logger.info(f"Admin {admin_email} removed {email} from query whitelist")
            return {
                "success": True,
                "message": f"Successfully removed '{email}' from the query whitelist.",
            }
        else:
            return {
                "success": False,
                "message": f"'{email}' was not found in the query whitelist.",
            }

    except PermissionError as e:
        return {
            "success": False,
            "message": f"Permission denied: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Error removing from query whitelist: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}",
        }


# Tool definitions
add_to_teach_whitelist_tool = Tool(
    name="add_to_teach_whitelist",
    description="Add a user to the TEACH whitelist specifically, allowing them to add/modify content in the knowledge base. ADMIN ONLY. ONLY use when the administrator EXPLICITLY requests 'teach' or 'teaching' permissions. If the request is vague (like 'add to users' or 'add to list'), ask for clarification about which specific whitelist.",
    parameters=[
        ToolParameter(
            name="email",
            type=ParameterType.STRING,
            description="Email address or domain pattern to add (e.g., 'user@example.com' or '@example.com' for entire domain)",
            required=True,
        ),
    ],
    function=add_to_teach_whitelist,
    returns_attachment=False,
)

remove_from_teach_whitelist_tool = Tool(
    name="remove_from_teach_whitelist",
    description="Remove a user from the TEACH whitelist specifically, revoking their ability to add/modify content in the knowledge base. ADMIN ONLY. ONLY use when the administrator EXPLICITLY requests to remove 'teach' or 'teaching' permissions. If the request is vague, ask for clarification.",
    parameters=[
        ToolParameter(
            name="email",
            type=ParameterType.STRING,
            description="Email address or domain pattern to remove",
            required=True,
        ),
    ],
    function=remove_from_teach_whitelist,
    returns_attachment=False,
)

add_to_query_whitelist_tool = Tool(
    name="add_to_query_whitelist",
    description="Add a user to the QUERY whitelist specifically, allowing them to ask questions. ADMIN ONLY. ONLY use when the administrator EXPLICITLY requests 'query' or 'asking questions' permissions. If the request is vague (like 'add to users' or 'add to list'), ask for clarification about which specific whitelist.",
    parameters=[
        ToolParameter(
            name="email",
            type=ParameterType.STRING,
            description="Email address or domain pattern to add (e.g., 'user@example.com' or '@example.com' for entire domain)",
            required=True,
        ),
    ],
    function=add_to_query_whitelist,
    returns_attachment=False,
)

remove_from_query_whitelist_tool = Tool(
    name="remove_from_query_whitelist",
    description="Remove a user from the QUERY whitelist specifically, revoking their ability to ask questions. ADMIN ONLY. ONLY use when the administrator EXPLICITLY requests to remove 'query' or 'asking questions' permissions. If the request is vague, ask for clarification.",
    parameters=[
        ToolParameter(
            name="email",
            type=ParameterType.STRING,
            description="Email address or domain pattern to remove",
            required=True,
        ),
    ],
    function=remove_from_query_whitelist,
    returns_attachment=False,
)

# Register tools
register_tool(add_to_teach_whitelist_tool)
register_tool(remove_from_teach_whitelist_tool)
register_tool(add_to_query_whitelist_tool)
register_tool(remove_from_query_whitelist_tool)
