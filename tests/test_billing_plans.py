"""Tests for billing plan configuration and limit enforcement."""

import pytest

from src.billing.plans import (
    PLAN_DISPLAY_NAMES,
    PLAN_FALLBACK_PRICES,
    PLAN_QUERY_LIMITS,
    PLAN_STORAGE_LIMITS_MB,
    check_query_limit,
    check_storage_limit,
    get_effective_plan,
    get_query_limit,
    get_storage_limit_mb,
)
from src.platform.models import PlanTier, SubscriptionStatus


class TestPlanConfiguration:
    """Test plan limit constants are correctly defined."""

    def test_all_tiers_have_query_limits(self):
        for tier in PlanTier:
            assert tier in PLAN_QUERY_LIMITS

    def test_all_tiers_have_storage_limits(self):
        for tier in PlanTier:
            assert tier in PLAN_STORAGE_LIMITS_MB

    def test_all_tiers_have_display_names(self):
        for tier in PlanTier:
            assert tier in PLAN_DISPLAY_NAMES

    def test_free_has_zero_limits(self):
        assert PLAN_QUERY_LIMITS[PlanTier.FREE] == 0
        assert PLAN_STORAGE_LIMITS_MB[PlanTier.FREE] == 0

    def test_lite_limits(self):
        assert PLAN_QUERY_LIMITS[PlanTier.LITE] == 500
        assert PLAN_STORAGE_LIMITS_MB[PlanTier.LITE] == 2 * 1024

    def test_team_limits(self):
        assert PLAN_QUERY_LIMITS[PlanTier.TEAM] == 2000
        assert PLAN_STORAGE_LIMITS_MB[PlanTier.TEAM] == 10 * 1024

    def test_department_limits(self):
        assert PLAN_QUERY_LIMITS[PlanTier.DEPARTMENT] == 10000
        assert PLAN_STORAGE_LIMITS_MB[PlanTier.DEPARTMENT] == 50 * 1024

    def test_fallback_prices(self):
        assert PLAN_FALLBACK_PRICES[PlanTier.LITE] == 240
        assert PLAN_FALLBACK_PRICES[PlanTier.TEAM] == 588
        assert PLAN_FALLBACK_PRICES[PlanTier.DEPARTMENT] == 1788
        assert PLAN_FALLBACK_PRICES[PlanTier.FREE] is None


class TestEffectivePlan:
    """Test trialing tenants get Department access."""

    def test_trialing_gets_department(self):
        assert (
            get_effective_plan(PlanTier.FREE, SubscriptionStatus.TRIALING)
            == PlanTier.DEPARTMENT
        )

    def test_trialing_overrides_lite(self):
        assert (
            get_effective_plan(PlanTier.LITE, SubscriptionStatus.TRIALING)
            == PlanTier.DEPARTMENT
        )

    def test_active_keeps_plan(self):
        assert (
            get_effective_plan(PlanTier.LITE, SubscriptionStatus.ACTIVE)
            == PlanTier.LITE
        )

    def test_cancelled_keeps_plan(self):
        assert (
            get_effective_plan(PlanTier.FREE, SubscriptionStatus.CANCELLED)
            == PlanTier.FREE
        )


class TestQueryLimits:
    """Test query limit calculation."""

    def test_trialing_gets_department_limit(self):
        assert get_query_limit(PlanTier.FREE, SubscriptionStatus.TRIALING) == 10000

    def test_active_lite(self):
        assert get_query_limit(PlanTier.LITE, SubscriptionStatus.ACTIVE) == 500

    def test_active_team(self):
        assert get_query_limit(PlanTier.TEAM, SubscriptionStatus.ACTIVE) == 2000

    def test_cancelled_free(self):
        assert get_query_limit(PlanTier.FREE, SubscriptionStatus.CANCELLED) == 0


class TestStorageLimits:
    """Test storage limit calculation."""

    def test_trialing_gets_department_limit(self):
        assert (
            get_storage_limit_mb(PlanTier.FREE, SubscriptionStatus.TRIALING)
            == 50 * 1024
        )

    def test_active_lite(self):
        assert (
            get_storage_limit_mb(PlanTier.LITE, SubscriptionStatus.ACTIVE)
            == 2 * 1024
        )

    def test_cancelled_free(self):
        assert (
            get_storage_limit_mb(PlanTier.FREE, SubscriptionStatus.CANCELLED) == 0
        )


class TestCheckQueryLimit:
    """Test query limit enforcement."""

    def test_under_limit_passes(self):
        # Should not raise
        check_query_limit(PlanTier.LITE, SubscriptionStatus.ACTIVE, 499)

    def test_at_limit_raises(self):
        with pytest.raises(ValueError, match="500 queries"):
            check_query_limit(PlanTier.LITE, SubscriptionStatus.ACTIVE, 500)

    def test_over_limit_raises(self):
        with pytest.raises(ValueError, match="500 queries"):
            check_query_limit(PlanTier.LITE, SubscriptionStatus.ACTIVE, 1000)

    def test_free_always_raises(self):
        with pytest.raises(ValueError, match="trial has ended"):
            check_query_limit(PlanTier.FREE, SubscriptionStatus.CANCELLED, 0)

    def test_trialing_has_department_limit(self):
        # Should not raise even at 9999
        check_query_limit(PlanTier.FREE, SubscriptionStatus.TRIALING, 9999)

    def test_trialing_at_department_limit_raises(self):
        with pytest.raises(ValueError):
            check_query_limit(PlanTier.FREE, SubscriptionStatus.TRIALING, 10000)


class TestCheckStorageLimit:
    """Test storage limit enforcement."""

    def test_under_limit_passes(self):
        check_storage_limit(PlanTier.LITE, SubscriptionStatus.ACTIVE, 1000.0, 500.0)

    def test_would_exceed_raises(self):
        with pytest.raises(ValueError, match="2 GB"):
            check_storage_limit(
                PlanTier.LITE, SubscriptionStatus.ACTIVE, 2000.0, 100.0
            )

    def test_free_always_raises(self):
        with pytest.raises(ValueError, match="trial has ended"):
            check_storage_limit(
                PlanTier.FREE, SubscriptionStatus.CANCELLED, 0.0, 1.0
            )

    def test_trialing_has_department_limit(self):
        # 50 GB limit when trialing
        check_storage_limit(
            PlanTier.FREE, SubscriptionStatus.TRIALING, 40000.0, 10000.0
        )

    def test_trialing_exceeds_department_limit_raises(self):
        with pytest.raises(ValueError, match="50 GB"):
            check_storage_limit(
                PlanTier.FREE, SubscriptionStatus.TRIALING, 50000.0, 2000.0
            )
