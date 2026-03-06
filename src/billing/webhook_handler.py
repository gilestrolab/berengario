"""Paddle webhook event handlers — update tenant billing state in DB."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from src.billing.paddle_service import get_plan_for_price_id
from src.platform.models import PlanTier, SubscriptionStatus, Tenant

logger = logging.getLogger(__name__)


def _find_tenant(db: Session, event_data: dict[str, Any]) -> Tenant | None:
    """Locate the tenant for a webhook event.

    On subscription.created the tenant_id comes from custom_data.
    On all other events we look up by paddle_subscription_id.
    """
    # Try paddle_subscription_id first (present on updates/cancels)
    sub_id = event_data.get("id")
    if sub_id:
        tenant = (
            db.query(Tenant)
            .filter(Tenant.paddle_subscription_id == sub_id)
            .first()
        )
        if tenant:
            return tenant

    # Fallback: custom_data.tenant_id (present on new subscriptions)
    custom_data = event_data.get("custom_data") or {}
    tenant_id = custom_data.get("tenant_id")
    if tenant_id:
        return db.query(Tenant).filter(Tenant.id == tenant_id).first()

    return None


def _first_price_id(event_data: dict[str, Any]) -> str | None:
    """Extract the first price ID from subscription items."""
    items = event_data.get("items") or []
    if items:
        price = items[0].get("price") or {}
        return price.get("id")
    return None


def handle_subscription_created(db: Session, event_data: dict[str, Any]) -> None:
    """subscription.created — new subscription activated."""
    tenant = _find_tenant(db, event_data)
    if not tenant:
        logger.warning(
            "subscription.created: tenant not found for event %s",
            event_data.get("id"),
        )
        return

    price_id = _first_price_id(event_data)
    plan = get_plan_for_price_id(price_id) if price_id else None
    if plan:
        tenant.plan = plan

    tenant.paddle_customer_id = event_data.get("customer_id")
    tenant.paddle_subscription_id = event_data.get("id")
    tenant.subscription_status = SubscriptionStatus.ACTIVE
    tenant.trial_ends_at = None
    tenant.paddle_subscription_scheduled_change = None

    db.commit()
    logger.info(
        "subscription.created: tenant %s → plan=%s, status=active",
        tenant.id,
        tenant.plan.value,
    )


def handle_subscription_updated(db: Session, event_data: dict[str, Any]) -> None:
    """subscription.updated — plan change, payment method update, or scheduled change."""
    tenant = _find_tenant(db, event_data)
    if not tenant:
        logger.warning(
            "subscription.updated: tenant not found for sub %s",
            event_data.get("id"),
        )
        return

    # Update plan if the price changed
    price_id = _first_price_id(event_data)
    if price_id:
        plan = get_plan_for_price_id(price_id)
        if plan:
            tenant.plan = plan

    # Map Paddle status to our enum
    paddle_status = event_data.get("status")
    status_map = {
        "active": SubscriptionStatus.ACTIVE,
        "trialing": SubscriptionStatus.TRIALING,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELLED,
        "paused": SubscriptionStatus.CANCELLED,
    }
    if paddle_status in status_map:
        tenant.subscription_status = status_map[paddle_status]

    # Store scheduled change (e.g. pending cancellation at period end)
    scheduled = event_data.get("scheduled_change")
    tenant.paddle_subscription_scheduled_change = scheduled

    db.commit()
    logger.info(
        "subscription.updated: tenant %s → plan=%s, status=%s",
        tenant.id,
        tenant.plan.value,
        tenant.subscription_status.value,
    )


def handle_subscription_canceled(db: Session, event_data: dict[str, Any]) -> None:
    """subscription.canceled — subscription fully cancelled, downgrade to Free."""
    tenant = _find_tenant(db, event_data)
    if not tenant:
        logger.warning(
            "subscription.canceled: tenant not found for sub %s",
            event_data.get("id"),
        )
        return

    tenant.plan = PlanTier.FREE
    tenant.subscription_status = SubscriptionStatus.CANCELLED
    tenant.paddle_subscription_scheduled_change = None

    db.commit()
    logger.info("subscription.canceled: tenant %s downgraded to free", tenant.id)


def handle_subscription_past_due(db: Session, event_data: dict[str, Any]) -> None:
    """subscription.past_due — payment failed."""
    tenant = _find_tenant(db, event_data)
    if not tenant:
        logger.warning(
            "subscription.past_due: tenant not found for sub %s",
            event_data.get("id"),
        )
        return

    tenant.subscription_status = SubscriptionStatus.PAST_DUE
    db.commit()
    logger.info("subscription.past_due: tenant %s", tenant.id)


# Dispatcher mapping event_type -> handler
EVENT_HANDLERS: dict[str, Any] = {
    "subscription.created": handle_subscription_created,
    "subscription.updated": handle_subscription_updated,
    "subscription.canceled": handle_subscription_canceled,
    "subscription.past_due": handle_subscription_past_due,
}


def dispatch_event(db: Session, event_type: str, event_data: dict[str, Any]) -> bool:
    """Dispatch a Paddle event to the appropriate handler.

    Returns True if the event was handled, False if ignored.
    """
    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        handler(db, event_data)
        return True
    logger.debug("Ignoring unhandled Paddle event: %s", event_type)
    return False
