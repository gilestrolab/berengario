"""
Platform health endpoint for the admin panel.

Returns platform DB status, cache stats, and tenant summary.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from src.platform_admin.models import PlatformHealth
from src.platform_admin.routes.auth import AdminSessionManager

logger = logging.getLogger(__name__)


def create_health_router(
    admin_session_manager: AdminSessionManager,
    db_manager,
    settings,
):
    """
    Create platform health router.

    Args:
        admin_session_manager: Admin session store.
        db_manager: TenantDBManager instance.
        settings: Application settings.

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix="/api/platform", tags=["platform"])

    @router.get("/health", response_model=PlatformHealth)
    async def platform_health(request: Request):
        """
        Get platform health status.

        The health endpoint is accessible without auth for Docker healthchecks,
        but only returns full details to authenticated admins.

        Args:
            request: FastAPI request.

        Returns:
            PlatformHealth.
        """
        # Basic health check (no auth required for Docker healthcheck)
        platform_db = db_manager.test_platform_connection()
        cache_stats = db_manager.get_cache_stats()

        # Tenant counts
        tenant_counts = {"active": 0, "suspended": 0, "provisioning": 0}
        try:
            from sqlalchemy import func

            from src.platform.models import Tenant

            with db_manager.get_platform_session() as session:
                counts = (
                    session.query(Tenant.status, func.count(Tenant.id))
                    .group_by(Tenant.status)
                    .all()
                )
                for status, count in counts:
                    key = status.value if hasattr(status, "value") else status
                    tenant_counts[key] = count
        except Exception as e:
            logger.warning(f"Failed to get tenant counts: {e}")

        return PlatformHealth(
            status="healthy" if platform_db else "unhealthy",
            platform_db=platform_db,
            cache_stats=cache_stats,
            tenant_counts=tenant_counts,
            encryption_enabled=bool(settings.master_encryption_key),
            storage_backend=settings.storage_backend,
            timestamp=datetime.now(UTC).isoformat(),
        )

    return router
