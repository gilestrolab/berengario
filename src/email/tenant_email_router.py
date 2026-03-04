"""
Tenant email routing for multi-tenant email processing.

Routes incoming emails to the correct tenant(s) based on sender email
address lookup in the platform TenantUser table. Handles permission
checks using TenantUser roles.
"""

import logging
from typing import Dict, List

from src.platform.component_factory import TenantComponentFactory, TenantComponents
from src.platform.db_manager import TenantDBManager
from src.platform.tenant_context import TenantContext

logger = logging.getLogger(__name__)


class TenantEmailRouter:
    """
    Routes emails to tenants based on sender lookup in TenantUser table.

    Uses database-backed TenantUser role checks. A single sender may belong
    to multiple tenants with different roles.

    Attributes:
        _db_manager: Platform DB manager for TenantUser lookups.
        _component_factory: Factory for per-tenant component stacks.
    """

    # Role hierarchy: admin > teacher > querier
    # admin/teacher can teach and query; querier can only query
    _TEACH_ROLES = {"admin", "teacher"}
    _QUERY_ROLES = {"admin", "teacher", "querier"}

    def __init__(
        self,
        db_manager: TenantDBManager,
        component_factory: TenantComponentFactory,
    ):
        """
        Initialize tenant email router.

        Args:
            db_manager: Platform DB manager for user lookups.
            component_factory: Factory for per-tenant components.
        """
        self._db_manager = db_manager
        self._component_factory = component_factory
        logger.info("TenantEmailRouter initialized")

    def resolve_sender(self, sender_email: str) -> List[Dict]:
        """
        Look up which tenants a sender belongs to.

        Queries TenantUser JOIN Tenant for active tenants only.

        Args:
            sender_email: Sender's email address.

        Returns:
            List of dicts with tenant_slug, tenant_id, role, tenant_name.
            Empty list if sender not found in any tenant.
        """
        from src.platform.models import Tenant, TenantStatus, TenantUser

        with self._db_manager.get_platform_session() as session:
            records = (
                session.query(TenantUser)
                .join(Tenant)
                .filter(
                    TenantUser.email == sender_email,
                    Tenant.status == TenantStatus.ACTIVE,
                )
                .all()
            )
            results = [
                {
                    "tenant_slug": r.tenant.slug,
                    "tenant_id": r.tenant_id,
                    "role": r.role.value if hasattr(r.role, "value") else r.role,
                    "tenant_name": r.tenant.name,
                }
                for r in records
            ]

        if results:
            slugs = [r["tenant_slug"] for r in results]
            logger.info(
                f"Resolved sender {sender_email} to {len(results)} tenant(s): {slugs}"
            )
        else:
            logger.info(f"Sender {sender_email} not found in any active tenant")

        return results

    def check_permission(self, role: str, action: str) -> bool:
        """
        Check if a role has permission for an action.

        Args:
            role: User role string ("admin", "teacher", "querier").
            action: Action to check ("teach" or "query").

        Returns:
            True if the role permits the action.
        """
        if action == "teach":
            return role in self._TEACH_ROLES
        elif action == "query":
            return role in self._QUERY_ROLES
        return False

    def get_components(self, tenant_slug: str) -> TenantComponents:
        """
        Get component stack for a tenant.

        Args:
            tenant_slug: Tenant slug identifier.

        Returns:
            TenantComponents with KB, RAG, query handler, etc.

        Raises:
            ValueError: If tenant not found or not active.
        """
        return self._component_factory.get_components_for_slug(tenant_slug)

    def get_tenant_context(self, tenant_slug: str) -> TenantContext:
        """
        Get TenantContext for path resolution and identity.

        Args:
            tenant_slug: Tenant slug identifier.

        Returns:
            TenantContext with paths, instance_name, organization, etc.
        """
        components = self.get_components(tenant_slug)
        return components.context
