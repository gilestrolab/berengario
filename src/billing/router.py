"""Billing router — checkout config, portal, webhook, downgrade, plan info."""

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from src.billing.paddle_service import (
    cancel_subscription,
    get_subscription_management_urls,
    verify_webhook_signature,
)
from src.billing.plans import (
    PLAN_DISPLAY_NAMES,
    PLAN_FALLBACK_PRICES,
    PLAN_QUERY_LIMITS,
    PLAN_STORAGE_LIMITS_MB,
    get_query_limit,
    get_storage_limit_mb,
)
from src.billing.webhook_handler import dispatch_event
from src.config import settings
from src.platform.models import PlanTier, SubscriptionStatus

logger = logging.getLogger(__name__)


def create_billing_router(platform_db_manager, require_admin, require_auth):
    """Create billing router with injected dependencies.

    Args:
        platform_db_manager: TenantDBManager for platform DB access.
        require_admin: Dependency that enforces admin access.
        require_auth: Dependency that enforces authentication.

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix="/api/billing", tags=["billing"])

    @router.get("/checkout-config")
    async def checkout_config(request: Request):
        """Return Paddle client-side config for initialising checkout.

        Only admins can trigger checkouts (they manage billing for the team).
        """
        session = require_admin(request)
        tenant_slug = session.tenant_slug

        with platform_db_manager.get_platform_session() as db:
            from src.platform.models import Tenant

            tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
            if not tenant:
                return JSONResponse(
                    status_code=404, content={"detail": "Tenant not found"}
                )

            return {
                "client_token": settings.paddle_client_token,
                "environment": settings.paddle_environment,
                "price_id_lite": settings.paddle_price_id_lite,
                "price_id_team": settings.paddle_price_id_team,
                "price_id_department": settings.paddle_price_id_department,
                "tenant_id": tenant.id,
                "email": session.email,
                "paddle_customer_id": tenant.paddle_customer_id,
                "current_plan": tenant.plan.value,
                "subscription_status": tenant.subscription_status.value,
                "paddle_subscription_id": tenant.paddle_subscription_id,
                "scheduled_change": tenant.paddle_subscription_scheduled_change,
            }

    @router.get("/portal")
    async def billing_portal(request: Request):
        """Return Paddle subscription management URLs (update payment, cancel)."""
        session = require_admin(request)
        tenant_slug = session.tenant_slug

        with platform_db_manager.get_platform_session() as db:
            from src.platform.models import Tenant

            tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
            if not tenant or not tenant.paddle_subscription_id:
                return JSONResponse(
                    status_code=404,
                    content={"detail": "No active subscription found"},
                )

            urls = await get_subscription_management_urls(
                tenant.paddle_subscription_id
            )
            if not urls:
                return JSONResponse(
                    status_code=502,
                    content={
                        "detail": "Could not fetch management URLs from Paddle"
                    },
                )

            return urls

    @router.post("/webhook")
    async def paddle_webhook(request: Request):
        """Receive and process Paddle webhook events.

        This endpoint is public but protected by HMAC signature verification.
        """
        raw_body = await request.body()
        signature = request.headers.get("Paddle-Signature", "")

        if not verify_webhook_signature(raw_body, signature):
            logger.warning("Paddle webhook signature verification failed")
            return Response(status_code=403)

        payload = await request.json()
        event_type = payload.get("event_type", "")
        event_data = payload.get("data", {})

        logger.info("Paddle webhook received: %s", event_type)

        with platform_db_manager.get_platform_session() as db:
            dispatch_event(db, event_type, event_data)

        return Response(status_code=200)

    @router.post("/downgrade-to-free")
    async def downgrade_to_free(request: Request):
        """Cancel Paddle subscription at period end, or directly downgrade."""
        session = require_admin(request)
        tenant_slug = session.tenant_slug

        with platform_db_manager.get_platform_session() as db:
            from src.platform.models import Tenant

            tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
            if not tenant:
                return JSONResponse(
                    status_code=404, content={"detail": "Tenant not found"}
                )

            if tenant.paddle_subscription_id and tenant.subscription_status in (
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAST_DUE,
                SubscriptionStatus.TRIALING,
            ):
                success = await cancel_subscription(
                    tenant.paddle_subscription_id,
                    effective_from="next_billing_period",
                )
                if not success:
                    return JSONResponse(
                        status_code=502,
                        content={
                            "detail": "Failed to cancel subscription with Paddle"
                        },
                    )
                return {
                    "detail": "Subscription will be cancelled at the end "
                    "of the current billing period"
                }

            # No active Paddle subscription — downgrade immediately
            tenant.plan = PlanTier.FREE
            tenant.subscription_status = SubscriptionStatus.CANCELLED
            tenant.paddle_subscription_scheduled_change = None

            return {"detail": "Downgraded to Free plan"}

    @router.get("/plan-info")
    async def plan_info(request: Request):
        """Return current plan, usage stats, and limits for the tenant."""
        session = require_auth(request)
        tenant_slug = session.tenant_slug

        with platform_db_manager.get_platform_session() as db:
            from src.platform.models import Tenant

            tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
            if not tenant:
                return JSONResponse(
                    status_code=404, content={"detail": "Tenant not found"}
                )

            plan = tenant.plan
            status = tenant.subscription_status
            query_limit = get_query_limit(plan, status)
            storage_limit_mb = get_storage_limit_mb(plan, status)

            # Count queries this month from tenant DB
            queries_this_month = _count_queries_this_month(
                platform_db_manager, tenant
            )

            # Calculate storage used
            storage_used_mb = _get_storage_used_mb(platform_db_manager, tenant)

            return {
                "plan": plan.value,
                "plan_display": PLAN_DISPLAY_NAMES.get(plan, plan.value),
                "subscription_status": status.value,
                "is_trialing": status == SubscriptionStatus.TRIALING,
                "trial_ends_at": (
                    tenant.trial_ends_at.isoformat()
                    if tenant.trial_ends_at
                    else None
                ),
                "queries_this_month": queries_this_month,
                "query_limit": query_limit,
                "storage_used_mb": round(storage_used_mb, 1),
                "storage_limit_mb": storage_limit_mb,
                "scheduled_change": tenant.paddle_subscription_scheduled_change,
                "plans": _get_all_plans_info(),
            }

    return router


def _count_queries_this_month(platform_db_manager, tenant) -> int:
    """Count query messages in the tenant DB for the current month."""
    from datetime import datetime

    from src.email.db_models import ConversationMessage

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        with platform_db_manager.get_tenant_session(tenant) as db:
            count = (
                db.query(ConversationMessage)
                .filter(
                    ConversationMessage.role == "user",
                    ConversationMessage.created_at >= month_start,
                )
                .count()
            )
            return count
    except Exception as e:
        logger.error("Failed to count queries for tenant %s: %s", tenant.slug, e)
        return 0


def _get_storage_used_mb(platform_db_manager, tenant) -> float:
    """Calculate total storage used by a tenant's documents in MB."""
    from src.email.db_models import DocumentDescription

    try:
        with platform_db_manager.get_tenant_session(tenant) as db:
            from sqlalchemy import func

            total_bytes = (
                db.query(func.sum(DocumentDescription.file_size))
                .scalar()
            )
            if total_bytes is None:
                return 0.0
            return total_bytes / (1024 * 1024)
    except Exception as e:
        logger.error(
            "Failed to get storage for tenant %s: %s", tenant.slug, e
        )
        return 0.0


def _get_all_plans_info() -> list[dict]:
    """Return info for all available plans."""
    plans = []
    for tier in [PlanTier.LITE, PlanTier.TEAM, PlanTier.DEPARTMENT]:
        plans.append(
            {
                "tier": tier.value,
                "display_name": PLAN_DISPLAY_NAMES[tier],
                "queries_per_month": PLAN_QUERY_LIMITS[tier],
                "storage_mb": PLAN_STORAGE_LIMITS_MB[tier],
                "storage_display": f"{PLAN_STORAGE_LIMITS_MB[tier] / 1024:.0f} GB",
                "fallback_price_gbp": PLAN_FALLBACK_PRICES.get(tier),
            }
        )
    return plans
