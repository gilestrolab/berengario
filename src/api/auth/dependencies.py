"""
FastAPI dependencies for authentication and session management.

Provides helper functions for session cookie management.
Note: require_auth and require_admin are defined in api.py since they
need access to the session_manager instance.
"""

from typing import Optional

from fastapi import Request, Response


def get_session_id(request: Request) -> Optional[str]:
    """Extract session ID from cookie."""
    return request.cookies.get("session_id")


def set_session_cookie(response: Response, session_id: str):
    """Set session ID cookie."""
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=3600 * 24 * 7,  # 7 days
        httponly=True,
        samesite="lax",
    )
