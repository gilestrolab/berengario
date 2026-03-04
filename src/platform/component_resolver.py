"""
Component resolver for bridging session state to tenant components.

Always resolves the active tenant from the session and returns
tenant-specific components via TenantComponentFactory.
"""

import logging

from src.platform.component_factory import TenantComponentFactory, TenantComponents

logger = logging.getLogger(__name__)


class ComponentResolver:
    """
    Resolves the correct TenantComponents for a given session.

    Routers call resolver.resolve(session) to get the component stack
    appropriate for the current user's active tenant.

    Attributes:
        _factory: TenantComponentFactory for component creation.
    """

    def __init__(self, component_factory: TenantComponentFactory, **_kwargs):
        """
        Initialize component resolver.

        Args:
            component_factory: Factory for creating tenant component stacks.
            **_kwargs: Ignored (backwards compat for callers passing multi_tenant=).
        """
        self._factory = component_factory
        logger.info("ComponentResolver initialized")

    def resolve(self, session) -> TenantComponents:
        """
        Resolve components for the given session.

        Looks up session.tenant_slug and returns tenant-specific
        components from the factory.

        Args:
            session: Session object with tenant_slug attribute.

        Returns:
            TenantComponents for the session's active tenant.

        Raises:
            ValueError: If no tenant selected in session or factory missing.
        """
        slug = getattr(session, "tenant_slug", None)
        if not slug:
            raise ValueError(
                "No tenant selected. User must select a tenant before accessing resources."
            )

        if not self._factory:
            raise ValueError("No component factory configured")

        return self._factory.get_components_for_slug(slug)
