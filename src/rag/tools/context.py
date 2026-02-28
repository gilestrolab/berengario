"""
Thread-safe context management for RAG tools.

Uses contextvars to provide thread-safe storage of user context for tool execution.
This replaces the global dictionary pattern with proper context isolation.
"""

import logging
from contextvars import ContextVar
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Context variables for thread-safe storage
_user_email: ContextVar[str] = ContextVar("user_email", default="unknown")
_is_admin: ContextVar[bool] = ContextVar("is_admin", default=False)
_is_email_request: ContextVar[bool] = ContextVar("is_email_request", default=False)
_kb_manager: ContextVar[Optional[Any]] = ContextVar("kb_manager", default=None)


def set_tool_context(
    user_email: str,
    is_admin: bool,
    is_email_request: bool = False,
    kb_manager: Optional[Any] = None,
) -> None:
    """
    Set the context for tool execution (called before tool execution).

    This function is thread-safe and uses contextvars to isolate context
    per request/thread/asyncio task.

    Args:
        user_email: Email of the user making the request
        is_admin: Whether the user is an admin
        is_email_request: Whether this request is from email (requires confirmation)
        kb_manager: Optional KnowledgeBaseManager instance (for MT per-tenant KB)
    """
    _user_email.set(user_email)
    _is_admin.set(is_admin)
    _is_email_request.set(is_email_request)
    _kb_manager.set(kb_manager)
    logger.debug(
        f"Tool context set: user={user_email}, admin={is_admin}, email={is_email_request}"
    )


def get_tool_context() -> Dict[str, any]:
    """
    Get the current tool context.

    Returns:
        Dictionary with context information:
            - user_email: Email of current user
            - is_admin: Admin status
            - is_email_request: Whether from email
    """
    return {
        "user_email": _user_email.get(),
        "is_admin": _is_admin.get(),
        "is_email_request": _is_email_request.get(),
    }


def clear_tool_context() -> None:
    """
    Clear the tool context after execution.

    Note: With contextvars, this is often unnecessary as context is automatically
    isolated per request. However, we keep this function for backward compatibility
    and explicit cleanup when needed.
    """
    _user_email.set("unknown")
    _is_admin.set(False)
    _is_email_request.set(False)
    _kb_manager.set(None)
    logger.debug("Tool context cleared")


def validate_admin_access() -> None:
    """
    Validate that the current requester is an admin.

    This is a helper function for tools that require admin privileges.

    Raises:
        PermissionError: If requester is not an admin
    """
    if not _is_admin.get():
        requester = _user_email.get()
        error_msg = f"Access denied: Only administrators can perform this action. Requester: {requester}"
        logger.warning(error_msg)
        raise PermissionError(error_msg)
    logger.debug(f"Admin access validated for {_user_email.get()}")


def get_user_email() -> str:
    """Get the current user's email address."""
    return _user_email.get()


def is_admin() -> bool:
    """Check if the current user is an admin."""
    return _is_admin.get()


def is_email_request() -> bool:
    """Check if the current request is from email."""
    return _is_email_request.get()


def get_kb_manager() -> Optional[Any]:
    """Get the current context's KnowledgeBaseManager (None in ST mode)."""
    return _kb_manager.get()
