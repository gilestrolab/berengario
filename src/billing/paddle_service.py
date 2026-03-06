"""Paddle Billing service — API helpers and webhook verification."""

import hashlib
import hmac
import logging
from typing import Any

import httpx

from src.config import settings
from src.platform.models import PlanTier

logger = logging.getLogger(__name__)

PADDLE_API_BASE = (
    "https://sandbox-api.paddle.com"
    if settings.paddle_environment == "sandbox"
    else "https://api.paddle.com"
)


# ---------------------------------------------------------------------------
# Price <-> Plan mapping
# ---------------------------------------------------------------------------


def get_plan_for_price_id(price_id: str) -> PlanTier | None:
    """Return the PlanTier matching a Paddle price ID, or None."""
    mapping = {
        settings.paddle_price_id_lite: PlanTier.LITE,
        settings.paddle_price_id_team: PlanTier.TEAM,
        settings.paddle_price_id_department: PlanTier.DEPARTMENT,
    }
    return mapping.get(price_id)


def get_price_id_for_plan(plan: PlanTier) -> str | None:
    """Return the Paddle price ID for a given plan tier."""
    mapping = {
        PlanTier.LITE: settings.paddle_price_id_lite,
        PlanTier.TEAM: settings.paddle_price_id_team,
        PlanTier.DEPARTMENT: settings.paddle_price_id_department,
    }
    return mapping.get(plan)


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verify the Paddle-Signature header using HMAC-SHA256.

    Paddle v2 webhook signature format:
        ts=<timestamp>;h1=<hex_hmac>

    The signed payload is ``<timestamp>:<raw_body>``.
    """
    secret = settings.paddle_webhook_secret
    if not secret:
        logger.warning("PADDLE_WEBHOOK_SECRET not configured — skipping verification")
        return True  # allow in dev when secret is not set

    try:
        parts = dict(p.split("=", 1) for p in signature_header.split(";"))
        ts = parts["ts"]
        h1 = parts["h1"]
    except (ValueError, KeyError):
        logger.warning("Malformed Paddle-Signature header")
        return False

    signed_payload = f"{ts}:{raw_body.decode()}".encode()
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, h1)


# ---------------------------------------------------------------------------
# Paddle API calls
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.paddle_api_key}",
        "Content-Type": "application/json",
    }


async def get_subscription(subscription_id: str) -> dict[str, Any] | None:
    """Fetch a subscription from the Paddle API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PADDLE_API_BASE}/subscriptions/{subscription_id}",
            headers=_headers(),
        )
        if resp.status_code != 200:
            logger.error(
                "Paddle API error fetching subscription %s: %s",
                subscription_id,
                resp.text,
            )
            return None
        return resp.json().get("data")


async def get_subscription_management_urls(
    subscription_id: str,
) -> dict[str, str] | None:
    """Return update_payment and cancel URLs for a subscription."""
    data = await get_subscription(subscription_id)
    if not data or "management_urls" not in data:
        return None
    return data["management_urls"]


async def cancel_subscription(
    subscription_id: str, effective_from: str = "next_billing_period"
) -> bool:
    """Cancel a subscription via the Paddle API.

    Args:
        subscription_id: The Paddle subscription ID.
        effective_from: "next_billing_period" (default) or "immediately".

    Returns:
        True if the cancellation request succeeded.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PADDLE_API_BASE}/subscriptions/{subscription_id}/cancel",
            headers=_headers(),
            json={"effective_from": effective_from},
        )
        if resp.status_code not in (200, 201):
            logger.error(
                "Paddle cancel failed for %s: %s", subscription_id, resp.text
            )
            return False
        return True
