"""Tests for Paddle webhook handler."""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.billing.webhook_handler import (
    dispatch_event,
    handle_subscription_canceled,
    handle_subscription_created,
    handle_subscription_past_due,
    handle_subscription_updated,
)
from src.platform.models import (
    PlanTier,
    PlatformBase,
    SubscriptionStatus,
    Tenant,
    TenantStatus,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with platform tables."""
    engine = create_engine("sqlite:///:memory:")
    PlatformBase.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def tenant(db_session):
    """Create a test tenant."""
    t = Tenant(
        id="tenant-123",
        slug="acme",
        name="Acme Corp",
        status=TenantStatus.ACTIVE,
        email_address="acme@berengar.io",
        plan=PlanTier.DEPARTMENT,
        subscription_status=SubscriptionStatus.TRIALING,
        db_name="berengario_tenant_acme",
        storage_path="tenants/acme",
    )
    db_session.add(t)
    db_session.commit()
    return t


class TestSubscriptionCreated:
    """Test subscription.created webhook handler."""

    @patch("src.billing.webhook_handler.get_plan_for_price_id")
    def test_creates_subscription(self, mock_plan, db_session, tenant):
        mock_plan.return_value = PlanTier.TEAM

        event_data = {
            "id": "sub_abc123",
            "customer_id": "ctm_xyz",
            "custom_data": {"tenant_id": "tenant-123"},
            "items": [{"price": {"id": "pri_team"}}],
        }

        handle_subscription_created(db_session, event_data)

        db_session.refresh(tenant)
        assert tenant.plan == PlanTier.TEAM
        assert tenant.subscription_status == SubscriptionStatus.ACTIVE
        assert tenant.paddle_customer_id == "ctm_xyz"
        assert tenant.paddle_subscription_id == "sub_abc123"
        assert tenant.trial_ends_at is None

    def test_missing_tenant_logs_warning(self, db_session):
        event_data = {
            "id": "sub_unknown",
            "custom_data": {"tenant_id": "nonexistent"},
        }
        # Should not raise
        handle_subscription_created(db_session, event_data)


class TestSubscriptionUpdated:
    """Test subscription.updated webhook handler."""

    @patch("src.billing.webhook_handler.get_plan_for_price_id")
    def test_updates_plan(self, mock_plan, db_session, tenant):
        tenant.paddle_subscription_id = "sub_abc123"
        db_session.commit()

        mock_plan.return_value = PlanTier.LITE

        event_data = {
            "id": "sub_abc123",
            "status": "active",
            "items": [{"price": {"id": "pri_lite"}}],
            "scheduled_change": None,
        }

        handle_subscription_updated(db_session, event_data)

        db_session.refresh(tenant)
        assert tenant.plan == PlanTier.LITE
        assert tenant.subscription_status == SubscriptionStatus.ACTIVE

    def test_stores_scheduled_change(self, db_session, tenant):
        tenant.paddle_subscription_id = "sub_abc123"
        db_session.commit()

        event_data = {
            "id": "sub_abc123",
            "status": "active",
            "items": [],
            "scheduled_change": {"action": "cancel", "effective_at": "2026-06-01"},
        }

        handle_subscription_updated(db_session, event_data)

        db_session.refresh(tenant)
        assert tenant.paddle_subscription_scheduled_change == {
            "action": "cancel",
            "effective_at": "2026-06-01",
        }


class TestSubscriptionCanceled:
    """Test subscription.canceled webhook handler."""

    def test_downgrades_to_free(self, db_session, tenant):
        tenant.paddle_subscription_id = "sub_abc123"
        tenant.plan = PlanTier.TEAM
        tenant.subscription_status = SubscriptionStatus.ACTIVE
        db_session.commit()

        event_data = {"id": "sub_abc123"}

        handle_subscription_canceled(db_session, event_data)

        db_session.refresh(tenant)
        assert tenant.plan == PlanTier.FREE
        assert tenant.subscription_status == SubscriptionStatus.CANCELLED


class TestSubscriptionPastDue:
    """Test subscription.past_due webhook handler."""

    def test_marks_past_due(self, db_session, tenant):
        tenant.paddle_subscription_id = "sub_abc123"
        tenant.subscription_status = SubscriptionStatus.ACTIVE
        db_session.commit()

        event_data = {"id": "sub_abc123"}

        handle_subscription_past_due(db_session, event_data)

        db_session.refresh(tenant)
        assert tenant.subscription_status == SubscriptionStatus.PAST_DUE


class TestDispatchEvent:
    """Test event dispatcher."""

    def test_dispatches_known_event(self, db_session, tenant):
        tenant.paddle_subscription_id = "sub_abc123"
        db_session.commit()

        result = dispatch_event(
            db_session, "subscription.past_due", {"id": "sub_abc123"}
        )
        assert result is True

    def test_ignores_unknown_event(self, db_session):
        result = dispatch_event(db_session, "transaction.completed", {})
        assert result is False
