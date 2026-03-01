"""
Component resolver for bridging session state to tenant components.

In single-tenant (ST) mode, always returns the default components.
In multi-tenant (MT) mode, resolves the active tenant from the session
and returns tenant-specific components via TenantComponentFactory.
"""

import logging
from typing import Optional

from src.platform.component_factory import TenantComponentFactory, TenantComponents

logger = logging.getLogger(__name__)


class ComponentResolver:
    """
    Resolves the correct TenantComponents for a given session.

    Routers call resolver.resolve(session) to get the component stack
    appropriate for the current user's active tenant.

    Attributes:
        _multi_tenant: Whether multi-tenant mode is enabled.
        _factory: TenantComponentFactory for MT component creation.
        _default: Pre-built TenantComponents for ST fallback.
    """

    def __init__(
        self,
        multi_tenant: bool,
        component_factory: Optional[TenantComponentFactory] = None,
        default_components: Optional[TenantComponents] = None,
    ):
        """
        Initialize component resolver.

        Args:
            multi_tenant: Whether multi-tenant mode is active.
            component_factory: Factory for creating tenant component stacks (MT).
            default_components: Pre-built default components (ST).
        """
        self._multi_tenant = multi_tenant
        self._factory = component_factory
        self._default = default_components

        mode = "multi-tenant" if multi_tenant else "single-tenant"
        logger.info(f"ComponentResolver initialized in {mode} mode")

    def resolve(self, session) -> TenantComponents:
        """
        Resolve components for the given session.

        In ST mode, returns default components.
        In MT mode, looks up session.tenant_slug and returns
        tenant-specific components from the factory.

        Args:
            session: Session object with optional tenant_slug attribute.

        Returns:
            TenantComponents for the session's active tenant.

        Raises:
            ValueError: If MT mode but no tenant selected in session,
                or if factory/default components are missing.
        """
        if not self._multi_tenant:
            if self._default is None:
                raise ValueError("No default components configured for ST mode")
            return self._default

        # MT mode: resolve from session's active tenant
        slug = getattr(session, "tenant_slug", None)
        if not slug:
            raise ValueError(
                "No tenant selected. User must select a tenant before accessing resources."
            )

        if not self._factory:
            raise ValueError("No component factory configured for MT mode")

        return self._factory.get_components_for_slug(slug)
