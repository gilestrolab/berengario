"""Subscription plan configuration and limit enforcement."""

from src.platform.models import PlanTier, SubscriptionStatus

# Queries per month per plan (0 = no queries allowed)
PLAN_QUERY_LIMITS: dict[PlanTier, int] = {
    PlanTier.FREE: 0,
    PlanTier.LITE: 500,
    PlanTier.TEAM: 2000,
    PlanTier.DEPARTMENT: 10000,
}

# Storage limits in MB per plan (0 = no new uploads)
PLAN_STORAGE_LIMITS_MB: dict[PlanTier, int] = {
    PlanTier.FREE: 0,
    PlanTier.LITE: 2 * 1024,  # 2 GB
    PlanTier.TEAM: 10 * 1024,  # 10 GB
    PlanTier.DEPARTMENT: 50 * 1024,  # 50 GB
}

PLAN_DISPLAY_NAMES: dict[PlanTier, str] = {
    PlanTier.FREE: "Free",
    PlanTier.LITE: "Lite",
    PlanTier.TEAM: "Team",
    PlanTier.DEPARTMENT: "Department",
}

# Fallback GBP prices shown when Paddle.js hasn't loaded yet.
# Actual prices (incl. currency localisation) come from Paddle PricePreview.
PLAN_FALLBACK_PRICES: dict[PlanTier, int | None] = {
    PlanTier.FREE: None,
    PlanTier.LITE: 240,  # GBP/year
    PlanTier.TEAM: 588,  # GBP/year
    PlanTier.DEPARTMENT: 1788,  # GBP/year
}


def get_effective_plan(
    plan: PlanTier,
    subscription_status: SubscriptionStatus,
) -> PlanTier:
    """Return effective plan tier (trialing tenants get Department access)."""
    if subscription_status == SubscriptionStatus.TRIALING:
        return PlanTier.DEPARTMENT
    return plan


def get_query_limit(
    plan: PlanTier,
    subscription_status: SubscriptionStatus,
) -> int:
    """Return the monthly query limit for a tenant."""
    effective = get_effective_plan(plan, subscription_status)
    return PLAN_QUERY_LIMITS[effective]


def get_storage_limit_mb(
    plan: PlanTier,
    subscription_status: SubscriptionStatus,
) -> int:
    """Return the storage limit in MB for a tenant."""
    effective = get_effective_plan(plan, subscription_status)
    return PLAN_STORAGE_LIMITS_MB[effective]


def check_query_limit(
    plan: PlanTier,
    subscription_status: SubscriptionStatus,
    current_month_queries: int,
) -> None:
    """Raise ValueError if the next query would exceed the plan limit."""
    limit = get_query_limit(plan, subscription_status)
    if current_month_queries >= limit:
        plan_name = PLAN_DISPLAY_NAMES.get(plan, plan.value)
        if limit == 0:
            raise ValueError(
                "Your trial has ended. Please choose a plan to continue querying."
            )
        raise ValueError(
            f"Your {plan_name} plan allows {limit:,} queries per month. "
            f"You have used {current_month_queries:,}. "
            "Please upgrade your plan for more queries."
        )


def check_storage_limit(
    plan: PlanTier,
    subscription_status: SubscriptionStatus,
    current_storage_mb: float,
    new_file_size_mb: float,
) -> None:
    """Raise ValueError if adding a file would exceed the storage limit."""
    limit = get_storage_limit_mb(plan, subscription_status)
    if limit == 0:
        raise ValueError(
            "Your trial has ended. Please choose a plan to upload documents."
        )
    if current_storage_mb + new_file_size_mb > limit:
        plan_name = PLAN_DISPLAY_NAMES.get(plan, plan.value)
        limit_display = f"{limit / 1024:.0f} GB" if limit >= 1024 else f"{limit} MB"
        raise ValueError(
            f"Your {plan_name} plan allows {limit_display} of document storage. "
            f"Current usage: {current_storage_mb / 1024:.1f} GB. "
            "Please upgrade your plan for more storage."
        )
