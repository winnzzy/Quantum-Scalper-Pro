"""Subscription enforcement middleware and dependencies.

Provides FastAPI dependencies for:
- Requiring active subscription
- Feature-gating by plan tier
- Rate limiting by plan
- Device limit enforcement
- Grace period handling
"""
from datetime import datetime, timezone
from functools import wraps
from typing import Optional, List, Callable, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.database import async_session
from app.core.logging import logger
from app.core.redis import redis_client
from app.models.subscription import SubscriptionStatus, CustomerSubscription
from app.models.user import User
from app.services.subscription_service import subscription_service


security = HTTPBearer(auto_error=False)


# ──────────────────────────────────────────────────────────────────────
# Subscription Status Dependency
# ──────────────────────────────────────────────────────────────────────

async def get_active_subscription(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency that requires an active subscription.

    Returns subscription info dict or raises HTTP 403.
    Allows trialing, active, and past_due (grace period) statuses.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    subscription = await subscription_service.get_user_subscription(user.id)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "subscription_required",
                "message": "An active subscription is required to access this feature.",
                "upgrade_url": "/pricing",
            },
        )

    allowed_statuses = [
        SubscriptionStatus.ACTIVE.value,
        SubscriptionStatus.TRIALING.value,
        SubscriptionStatus.PAST_DUE.value,  # Grace period
    ]

    if subscription["status"] not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "subscription_inactive",
                "message": f"Subscription is {subscription['status']}. Please update your billing.",
                "status": subscription["status"],
                "billing_portal": "/api/v1/subscription/billing-portal",
            },
        )

    # Add subscription to request state for downstream use
    request.state.subscription = subscription
    return subscription


async def require_subscription(request: Request) -> dict:
    """Alias — same behavior, explicit naming."""
    return await get_active_subscription(request)


# ──────────────────────────────────────────────────────────────────────
# Feature-Gating Dependencies
# ──────────────────────────────────────────────────────────────────────

def require_feature(feature_name: str):
    """Create a FastAPI dependency that checks if the user's plan includes a feature.

    Usage:
        @router.get("/ai-signals", dependencies=[Depends(require_feature("ai_filter"))])
        async def get_ai_signals():
            ...
    """
    async def _check_feature(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        has_access = await subscription_service.check_feature_access(user.id, feature_name)
        if not has_access:
            plan_tier = "free"
            subscription = await subscription_service.get_user_subscription(user.id)
            if subscription:
                plan_tier = subscription.get("plan_tier", "free")

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "feature_not_included",
                    "message": f"Feature '{feature_name}' is not included in your current plan ({plan_tier}).",
                    "feature": feature_name,
                    "current_plan": plan_tier,
                    "upgrade_url": "/pricing",
                },
            )
        return True

    return _check_feature


def require_plan_tier(minimum_tier: str):
    """Require a minimum plan tier.

    Tiers: free < starter < professional < enterprise

    Usage:
        @router.post("/optimize", dependencies=[Depends(require_plan_tier("professional"))])
        async def optimize_strategy():
            ...
    """
    tier_hierarchy = {
        "free": 0,
        "starter": 1,
        "professional": 2,
        "enterprise": 3,
    }

    async def _check_tier(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        subscription = await subscription_service.get_user_subscription(user.id)
        current_tier = subscription.get("plan_tier", "free") if subscription else "free"
        current_level = tier_hierarchy.get(current_tier, 0)
        required_level = tier_hierarchy.get(minimum_tier, 0)

        if current_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "plan_upgrade_required",
                    "message": f"This feature requires the {minimum_tier.title()} plan or higher.",
                    "current_plan": current_tier,
                    "required_plan": minimum_tier,
                    "upgrade_url": "/pricing",
                },
            )
        return True

    return _check_tier


# ──────────────────────────────────────────────────────────────────────
# Plan Limits Dependency
# ──────────────────────────────────────────────────────────────────────

def check_plan_limit(limit_type: str, current_count: int):
    """Check if user is within plan limits.

    Usage:
        async def create_strategy(
            current_count: int = Depends(get_user_strategy_count),
            _: bool = Depends(check_plan_limit("strategies", current_count)),
        ):
            ...
    """
    async def _check_limit(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        within_limit = await subscription_service.check_plan_limits(
            user.id, limit_type, current_count
        )
        if not within_limit:
            subscription = await subscription_service.get_user_subscription(user.id)
            plan_tier = subscription.get("plan_tier", "free") if subscription else "free"

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "limit_reached",
                    "message": f"You've reached the {limit_type} limit for your {plan_tier} plan.",
                    "limit_type": limit_type,
                    "current_plan": plan_tier,
                    "upgrade_url": "/pricing",
                },
            )
        return True

    return _check_limit


# ──────────────────────────────────────────────────────────────────────
# Trial Expiry Warning Middleware
# ──────────────────────────────────────────────────────────────────────

async def check_trial_expiry(request: Request, call_next):
    """Middleware that adds trial expiry warnings to response headers."""
    response = await call_next(request)

    user = getattr(request.state, "user", None)
    if user:
        subscription = await subscription_service.get_user_subscription(user.id)
        if subscription and subscription.get("is_trial"):
            trial_end = subscription.get("trial_end")
            if trial_end:
                trial_end_dt = datetime.fromisoformat(trial_end)
                days_left = (trial_end_dt - datetime.now(timezone.utc)).days

                response.headers["X-Trial-Days-Left"] = str(max(0, days_left))
                response.headers["X-Trial-Ends-At"] = trial_end

                if days_left <= 3:
                    response.headers["X-Trial-Warning"] = (
                        f"Your trial expires in {days_left} day(s). "
                        f"Subscribe now to avoid interruption."
                    )

    return response


# ──────────────────────────────────────────────────────────────────────
# Rate Limiting by Plan
# ──────────────────────────────────────────────────────────────────────

class PlanRateLimiter:
    """Rate limiter that applies different limits based on subscription plan."""

    RATE_LIMITS = {
        "free": {"requests_per_minute": 30, "requests_per_hour": 500},
        "starter": {"requests_per_minute": 60, "requests_per_hour": 2000},
        "professional": {"requests_per_minute": 120, "requests_per_hour": 10000},
        "enterprise": {"requests_per_minute": 300, "requests_per_hour": 50000},
    }

    async def check_rate_limit(
        self,
        user_id: int,
        plan_tier: str = "free",
    ) -> bool:
        """Check if user is within rate limits. Returns True if allowed.
        
        Gracefully degrades: if Redis is unavailable, allows the request
        (fail-open for availability).
        """
        limits = self.RATE_LIMITS.get(plan_tier, self.RATE_LIMITS["free"])

        minute_key = f"rate_limit:{user_id}:minute"
        hour_key = f"rate_limit:{user_id}:hour"

        try:
            # Check per-minute limit
            minute_count = await redis_client.get(minute_key)
            if minute_count is not None and int(minute_count) >= limits["requests_per_minute"]:
                return False

            # Check per-hour limit
            hour_count = await redis_client.get(hour_key)
            if hour_count is not None and int(hour_count) >= limits["requests_per_hour"]:
                return False

            # Increment both counters using pipeline
            await redis_client.pipeline_execute([
                ("incr", {"name": minute_key}),
                ("expire", {"name": minute_key, "time": 60}),
                ("incr", {"name": hour_key}),
                ("expire", {"name": hour_key, "time": 3600}),
            ])

            return True

        except Exception as e:
            # Fail-open: if Redis is down, allow requests to maintain availability
            from app.core.logging import logger
            logger.warning(f"Rate limit check failed for user {user_id}, allowing request: {e}")
            return True


plan_rate_limiter = PlanRateLimiter()


async def enforce_rate_limit(request: Request):
    """FastAPI dependency for plan-based rate limiting."""
    user = getattr(request.state, "user", None)
    if not user:
        return

    subscription = await subscription_service.get_user_subscription(user.id)
    plan_tier = subscription.get("plan_tier", "free") if subscription else "free"

    allowed = await plan_rate_limiter.check_rate_limit(user.id, plan_tier)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Rate limit exceeded for your plan. Please upgrade or wait.",
                "current_plan": plan_tier,
                "upgrade_url": "/pricing",
            },
        )