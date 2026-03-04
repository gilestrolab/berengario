"""
Shared helpers for route factories.

Eliminates duplicated ST/MT component resolution and session email extraction
patterns across route files.
"""


def resolve_component(component_resolver, session, attr: str, default):
    """
    Resolve a tenant-specific component or fall back to the ST default.

    Args:
        component_resolver: ComponentResolver instance (None in ST mode).
        session: Authenticated session (carries tenant context in MT mode).
        attr: Attribute name on TenantComponents (e.g. "conversation_manager").
        default: Default component instance used in ST mode.

    Returns:
        The resolved component for the current tenant, or *default*.
    """
    if component_resolver:
        return getattr(component_resolver.resolve(session), attr)
    return default


def get_session_email(session, fallback_prefix: str = "web_user") -> str:
    """
    Extract the authenticated email from a session, with a stable fallback.

    Args:
        session: Authenticated session object.
        fallback_prefix: Prefix for the generated identifier when no email
            is available (default ``"web_user"``).

    Returns:
        The session email, or ``"{fallback_prefix}_{session_id[:8]}"``.
    """
    if hasattr(session, "email") and session.email:
        return session.email
    return f"{fallback_prefix}_{session.session_id[:8]}"
