"""Subscription management service.

Business logic for:
- Plan catalog management
- Subscription lifecycle (create, upgrade, downgrade, cancel)
- Trial account management
- License key generation
- Feature access control
- Plan limits enforcement
"""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal

from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.core.logging import logger
from app.core.redis import redis_client
from app.models.subscription import (
    SubscriptionPlanConfig, CustomerSubscription, Payment,
    SubscriptionStatus, BillingInterval, PlanTier, PaymentStatus,
)
from app.models.user import User, SubscriptionPlan
from app.services.stripe_service import stripe_service


class SubscriptionService:
    """Subscription lifecycle management."""

    # ──────────────────────────────────────────────────────────────────
    # Plan Catalog
    # ──────────────────────────────────────────────────────────────────

    async def get_plans(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all available subscription plans."""
        async with async_session() as session:
            query = select(SubscriptionPlanConfig).order_by(SubscriptionPlanConfig.sort_order)
            if active_only:
                query = query.where(SubscriptionPlanConfig.is_active == True)
            result = await session.execute(query)
            plans = result.scalars().all()

            return [
                {
                    "id": p.id,
                    "tier": p.plan_tier.value,
                    "billing_interval": p.billing_interval.value,
                    "price": float(p.price),
                    "currency": p.currency,
                    "stripe_price_id": p.stripe_price_id,
                    "display_name": p.display_name,
                    "description": p.description,
                    "max_devices": p.max_devices,
                    "max_strategies": p.max_strategies,
                    "max_broker_accounts": p.max_broker_accounts,
                    "max_backtests_per_day": p.max_backtests_per_day,
                    "max_api_calls_per_day": p.max_api_calls_per_day,
                    "features": p.features or [],
                    "trial_days": p.trial_days,
                }
                for p in plans
            ]

    async def seed_default_plans(self):
        """Seed default subscription plans if none exist."""
        async with async_session() as session:
            count = await session.execute(select(func.count(SubscriptionPlanConfig.id)))
            if count.scalar() > 0:
                return

            plans = [
                SubscriptionPlanConfig(
                    plan_tier=PlanTier.FREE,
                    billing_interval=BillingInterval.MONTHLY,
                    price=Decimal("0"),
                    display_name="Free",
                    description="Get started with paper trading",
                    max_devices=1,
                    max_strategies=2,
                    max_broker_accounts=1,
                    max_backtests_per_day=3,
                    max_api_calls_per_day=100,
                    features=["paper_trading", "basic_strategies", "basic_analytics"],
                    trial_days=0,
                    sort_order=0,
                    stripe_price_id=None,
                ),
                SubscriptionPlanConfig(
                    plan_tier=PlanTier.STARTER,
                    billing_interval=BillingInterval.MONTHLY,
                    price=Decimal("29.99"),
                    display_name="Starter",
                    description="Live trading with essential strategies",
                    max_devices=1,
                    max_strategies=5,
                    max_broker_accounts=1,
                    max_backtests_per_day=20,
                    max_api_calls_per_day=1000,
                    features=[
                        "paper_trading", "live_trading", "basic_strategies",
                        "email_notifications", "backtesting", "basic_analytics",
                    ],
                    trial_days=7,
                    sort_order=1,
                ),
                SubscriptionPlanConfig(
                    plan_tier=PlanTier.STARTER,
                    billing_interval=BillingInterval.ANNUAL,
                    price=Decimal("299.90"),
                    display_name="Starter Annual",
                    description="Live trading — save 17%",
                    max_devices=1,
                    max_strategies=5,
                    max_broker_accounts=1,
                    max_backtests_per_day=20,
                    max_api_calls_per_day=1000,
                    features=[
                        "paper_trading", "live_trading", "basic_strategies",
                        "email_notifications", "backtesting", "basic_analytics",
                    ],
                    trial_days=14,
                    sort_order=2,
                ),
                SubscriptionPlanConfig(
                    plan_tier=PlanTier.PROFESSIONAL,
                    billing_interval=BillingInterval.MONTHLY,
                    price=Decimal("79.99"),
                    display_name="Professional",
                    description="All strategies, AI filter, advanced analytics",
                    max_devices=3,
                    max_strategies=15,
                    max_broker_accounts=3,
                    max_backtests_per_day=100,
                    max_api_calls_per_day=5000,
                    features=[
                        "paper_trading", "live_trading", "all_strategies",
                        "ai_filter", "news_filter", "telegram_notifications",
                        "advanced_analytics", "backtesting", "optimization",
                        "multiple_brokers", "portfolio_management",
                    ],
                    trial_days=14,
                    sort_order=3,
                ),
                SubscriptionPlanConfig(
                    plan_tier=PlanTier.PROFESSIONAL,
                    billing_interval=BillingInterval.ANNUAL,
                    price=Decimal("799.90"),
                    display_name="Professional Annual",
                    description="All strategies — save 17%",
                    max_devices=3,
                    max_strategies=15,
                    max_broker_accounts=3,
                    max_backtests_per_day=100,
                    max_api_calls_per_day=5000,
                    features=[
                        "paper_trading", "live_trading", "all_strategies",
                        "ai_filter", "news_filter", "telegram_notifications",
                        "advanced_analytics", "backtesting", "optimization",
                        "multiple_brokers", "portfolio_management",
                    ],
                    trial_days=14,
                    sort_order=4,
                ),
                SubscriptionPlanConfig(
                    plan_tier=PlanTier.ENTERPRISE,
                    billing_interval=BillingInterval.MONTHLY,
                    price=Decimal("249.99"),
                    display_name="Enterprise",
                    description="Unlimited everything, white-label, API access",
                    max_devices=10,
                    max_strategies=50,
                    max_broker_accounts=10,
                    max_backtests_per_day=500,
                    max_api_calls_per_day=50000,
                    features=[
                        "paper_trading", "live_trading", "all_strategies",
                        "ai_filter", "news_filter", "telegram_notifications",
                        "advanced_analytics", "backtesting", "optimization",
                        "multiple_brokers", "portfolio_management",
                        "custom_strategies", "white_label", "api_access",
                        "dedicated_support", "priority_execution", "risk_alerts",
                    ],
                    trial_days=30,
                    sort_order=5,
                ),
                SubscriptionPlanConfig(
                    plan_tier=PlanTier.ENTERPRISE,
                    billing_interval=BillingInterval.ANNUAL,
                    price=Decimal("2499.90"),
                    display_name="Enterprise Annual",
                    description="Enterprise — save 17%",
                    max_devices=10,
                    max_strategies=50,
                    max_broker_accounts=10,
                    max_backtests_per_day=500,
                    max_api_calls_per_day=50000,
                    features=[
                        "paper_trading", "live_trading", "all_strategies",
                        "ai_filter", "news_filter", "telegram_notifications",
                        "advanced_analytics", "backtesting", "optimization",
                        "multiple_brokers", "portfolio_management",
                        "custom_strategies", "white_label", "api_access",
                        "dedicated_support", "priority_execution", "risk_alerts",
                    ],
                    trial_days=30,
                    sort_order=6,
                ),
            ]

            session.add_all(plans)
            await session.commit()
            logger.info(f"Seeded {len(plans)} subscription plans")

    # ──────────────────────────────────────────────────────────────────
    # Subscription Lifecycle
    # ──────────────────────────────────────────────────────────────────

    async def get_user_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get active subscription for a user."""
        async with async_session() as session:
            result = await session.execute(
                select(CustomerSubscription)
                .where(CustomerSubscription.user_id == user_id)
                .where(CustomerSubscription.status.in_([
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING,
                    SubscriptionStatus.PAST_DUE,
                    SubscriptionStatus.PAUSED,
                ]))
                .order_by(CustomerSubscription.created_at.desc())
                .limit(1)
            )
            sub = result.scalar_one_or_none()
            if not sub:
                return None

            plan_result = await session.execute(
                select(SubscriptionPlanConfig).where(SubscriptionPlanConfig.id == sub.plan_id)
            )
            plan = plan_result.scalar_one_or_none()

            return {
                "id": sub.id,
                "status": sub.status.value,
                "plan_tier": plan.plan_tier.value if plan else "free",
                "billing_interval": sub.billing_interval.value,
                "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                "cancel_at_period_end": sub.cancel_at_period_end,
                "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
                "is_trial": sub.status == SubscriptionStatus.TRIALING,
                "price": float(sub.price_snapshot) if sub.price_snapshot else 0,
                "currency": sub.currency,
                "stripe_subscription_id": sub.stripe_subscription_id,
                "stripe_customer_id": sub.stripe_customer_id,
                "max_devices": plan.max_devices if plan else 1,
                "max_strategies": plan.max_strategies if plan else 2,
                "features": plan.features if plan else [],
            }

    async def create_subscription(
        self,
        user_id: int,
        plan_id: int,
        billing_interval: BillingInterval = BillingInterval.MONTHLY,
        start_trial: bool = False,
        stripe_customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new subscription for a user."""
        async with async_session() as session:
            # Get plan
            plan = await session.get(SubscriptionPlanConfig, plan_id)
            if not plan:
                raise ValueError(f"Plan {plan_id} not found")

            # Check for existing active subscription
            existing = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == user_id,
                    CustomerSubscription.status.in_([
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ]),
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError("User already has an active subscription")

            now = datetime.now(timezone.utc)

            # Determine trial
            is_trial = start_trial and plan.trial_days > 0
            trial_end = now + timedelta(days=plan.trial_days) if is_trial else None

            # Create subscription
            subscription = CustomerSubscription(
                user_id=user_id,
                plan_id=plan_id,
                status=SubscriptionStatus.TRIALING if is_trial else SubscriptionStatus.ACTIVE,
                billing_interval=billing_interval,
                stripe_customer_id=stripe_customer_id,
                stripe_price_id=plan.stripe_price_id,
                price_snapshot=plan.price,
                currency=plan.currency,
                trial_start=now if is_trial else None,
                trial_end=trial_end,
                is_trial_used=is_trial,
                current_period_start=now,
                current_period_end=trial_end if is_trial else (
                    now + timedelta(days=30) if billing_interval == BillingInterval.MONTHLY
                    else now + timedelta(days=365)
                ),
            )
            session.add(subscription)

            # Update user model
            user = await session.get(User, user_id)
            if user:
                user.subscription_plan = SubscriptionPlan.PRO  # Map to legacy field
                user.subscription_expires_at = subscription.current_period_end
                if not user.license_key:
                    user.license_key = self.generate_license_key(plan.plan_tier.value)

            await session.commit()

            logger.info(f"Created subscription for user {user_id}: plan={plan.display_name}, trial={is_trial}")

            return {
                "subscription_id": subscription.id,
                "status": subscription.status.value,
                "plan": plan.display_name,
                "trial_end": trial_end.isoformat() if trial_end else None,
                "current_period_end": subscription.current_period_end.isoformat(),
                "license_key": user.license_key if user else None,
            }

    async def upgrade_subscription(
        self,
        user_id: int,
        new_plan_id: int,
    ) -> Dict[str, Any]:
        """Upgrade subscription to a higher plan with proration."""
        async with async_session() as session:
            # Get current subscription
            result = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == user_id,
                    CustomerSubscription.status.in_([
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ]),
                )
            )
            current_sub = result.scalar_one_or_none()
            if not current_sub:
                raise ValueError("No active subscription found")

            new_plan = await session.get(SubscriptionPlanConfig, new_plan_id)
            if not new_plan:
                raise ValueError(f"Plan {new_plan_id} not found")

            # Update in Stripe if connected
            if current_sub.stripe_subscription_id and new_plan.stripe_price_id:
                stripe_sub = await stripe_service.update_subscription(
                    current_sub.stripe_subscription_id,
                    new_plan.stripe_price_id,
                    proration_behavior="create_prorations",
                )

            # Update local record
            old_plan = await session.get(SubscriptionPlanConfig, current_sub.plan_id)
            current_sub.plan_id = new_plan_id
            current_sub.price_snapshot = new_plan.price
            current_sub.stripe_price_id = new_plan.stripe_price_id

            await session.commit()

            logger.info(f"User {user_id} upgraded from {old_plan.display_name if old_plan else '?'} to {new_plan.display_name}")

            return {
                "subscription_id": current_sub.id,
                "new_plan": new_plan.display_name,
                "new_price": float(new_plan.price),
                "prorated": bool(current_sub.stripe_subscription_id),
            }

    async def downgrade_subscription(
        self,
        user_id: int,
        new_plan_id: int,
    ) -> Dict[str, Any]:
        """Downgrade subscription at end of current period."""
        async with async_session() as session:
            result = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == user_id,
                    CustomerSubscription.status == SubscriptionStatus.ACTIVE,
                )
            )
            current_sub = result.scalar_one_or_none()
            if not current_sub:
                raise ValueError("No active subscription found")

            new_plan = await session.get(SubscriptionPlanConfig, new_plan_id)
            if not new_plan:
                raise ValueError(f"Plan {new_plan_id} not found")

            # Schedule downgrade in Stripe
            if current_sub.stripe_subscription_id and new_plan.stripe_price_id:
                await stripe_service.update_subscription(
                    current_sub.stripe_subscription_id,
                    new_plan.stripe_price_id,
                    proration_behavior="none",  # Apply at period end
                )

            # Store pending downgrade in metadata
            current_sub.metadata_json = {
                **(current_sub.metadata_json or {}),
                "pending_downgrade_plan_id": new_plan_id,
                "pending_downgrade_at": current_sub.current_period_end.isoformat() if current_sub.current_period_end else None,
            }

            await session.commit()

            return {
                "subscription_id": current_sub.id,
                "downgrade_to": new_plan.display_name,
                "effective_date": current_sub.current_period_end.isoformat() if current_sub.current_period_end else None,
            }

    async def cancel_subscription(
        self,
        user_id: int,
        at_period_end: bool = True,
        reason: Optional[str] = None,
        feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel user subscription."""
        async with async_session() as session:
            result = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == user_id,
                    CustomerSubscription.status.in_([
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                        SubscriptionStatus.PAST_DUE,
                    ]),
                )
            )
            subscription = result.scalar_one_or_none()
            if not subscription:
                raise ValueError("No active subscription found")

            if at_period_end:
                subscription.cancel_at_period_end = True
                subscription.metadata_json = {
                    **(subscription.metadata_json or {}),
                    "cancellation_reason": reason,
                    "cancellation_feedback": feedback,
                }
                # Cancel in Stripe at period end
                if subscription.stripe_subscription_id:
                    await stripe_service.cancel_subscription(
                        subscription.stripe_subscription_id,
                        at_period_end=True,
                        cancellation_reason=reason,
                    )
            else:
                subscription.status = SubscriptionStatus.CANCELED
                subscription.canceled_at = datetime.now(timezone.utc)
                subscription.ended_at = datetime.now(timezone.utc)
                # Cancel immediately in Stripe
                if subscription.stripe_subscription_id:
                    await stripe_service.cancel_subscription(
                        subscription.stripe_subscription_id,
                        at_period_end=False,
                    )

            await session.commit()

            logger.info(f"User {user_id} subscription canceled (at_period_end={at_period_end})")

            return {
                "subscription_id": subscription.id,
                "status": subscription.status.value,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "ends_at": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            }

    async def reactivate_subscription(self, user_id: int) -> Dict[str, Any]:
        """Reactivate a subscription that was set to cancel at period end."""
        async with async_session() as session:
            result = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == user_id,
                    CustomerSubscription.cancel_at_period_end == True,
                    CustomerSubscription.status.in_([
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.CANCELED,
                    ]),
                )
            )
            subscription = result.scalar_one_or_none()
            if not subscription:
                raise ValueError("No subscription to reactivate")

            subscription.cancel_at_period_end = False
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.canceled_at = None

            # Reactivate in Stripe
            if subscription.stripe_subscription_id:
                await stripe_service.reactivate_subscription(subscription.stripe_subscription_id)

            await session.commit()

            return {
                "subscription_id": subscription.id,
                "status": "active",
                "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            }

    # ──────────────────────────────────────────────────────────────────
    # Trial Management
    # ──────────────────────────────────────────────────────────────────

    async def start_trial(
        self,
        user_id: int,
        plan_tier: PlanTier = PlanTier.PROFESSIONAL,
    ) -> Dict[str, Any]:
        """Start a free trial for a user."""
        async with async_session() as session:
            # Check if user already used a trial
            existing_trial = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == user_id,
                    CustomerSubscription.is_trial_used == True,
                )
            )
            if existing_trial.scalar_one_or_none():
                raise ValueError("Trial already used. Please choose a paid plan.")

            # Find the monthly plan for this tier
            plan_result = await session.execute(
                select(SubscriptionPlanConfig).where(
                    SubscriptionPlanConfig.plan_tier == plan_tier,
                    SubscriptionPlanConfig.billing_interval == BillingInterval.MONTHLY,
                    SubscriptionPlanConfig.is_active == True,
                )
            )
            plan = plan_result.scalar_one_or_none()
            if not plan:
                raise ValueError(f"No plan found for tier {plan_tier.value}")

            return await self.create_subscription(
                user_id=user_id,
                plan_id=plan.id,
                billing_interval=BillingInterval.MONTHLY,
                start_trial=True,
            )

    async def convert_trial_to_paid(
        self,
        user_id: int,
        stripe_customer_id: str,
        stripe_price_id: str,
    ) -> Dict[str, Any]:
        """Convert a trial subscription to a paid subscription."""
        async with async_session() as session:
            result = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == user_id,
                    CustomerSubscription.status == SubscriptionStatus.TRIALING,
                )
            )
            subscription = result.scalar_one_or_none()
            if not subscription:
                raise ValueError("No trial subscription found")

            # Create Stripe subscription
            stripe_sub = await stripe_service.create_subscription(
                stripe_customer_id=stripe_customer_id,
                stripe_price_id=stripe_price_id,
            )

            subscription.stripe_subscription_id = stripe_sub.id
            subscription.stripe_customer_id = stripe_customer_id
            subscription.stripe_price_id = stripe_price_id
            subscription.status = SubscriptionStatus.ACTIVE

            await session.commit()

            return {
                "subscription_id": subscription.id,
                "status": "active",
                "stripe_subscription_id": stripe_sub.id,
            }

    # ──────────────────────────────────────────────────────────────────
    # Checkout Flow
    # ──────────────────────────────────────────────────────────────────

    async def create_checkout(
        self,
        user_id: int,
        plan_id: int,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """Create a Stripe Checkout session for subscription purchase."""
        async with async_session() as session:
            plan = await session.get(SubscriptionPlanConfig, plan_id)
            if not plan or not plan.stripe_price_id:
                raise ValueError("Plan not available for checkout")

            user = await session.get(User, user_id)
            if not user:
                raise ValueError("User not found")

            # Get or create Stripe customer
            customer = await stripe_service.get_or_create_customer(
                user_id=user_id,
                email=user.email,
                name=user.full_name,
            )

            # Create checkout session
            checkout = await stripe_service.create_checkout_session(
                stripe_customer_id=customer.id,
                stripe_price_id=plan.stripe_price_id,
                success_url=success_url,
                cancel_url=cancel_url,
                trial_days=plan.trial_days,
                metadata={
                    "user_id": str(user_id),
                    "plan_id": str(plan_id),
                    "plan_tier": plan.plan_tier.value,
                },
            )

            # Create pending subscription record
            await self.create_subscription(
                user_id=user_id,
                plan_id=plan_id,
                billing_interval=plan.billing_interval,
                start_trial=plan.trial_days > 0,
                stripe_customer_id=customer.id,
            )

            return {
                "checkout_url": checkout.url,
                "checkout_session_id": checkout.id,
                "expires_at": checkout.expires_at,
            }

    # ──────────────────────────────────────────────────────────────────
    # Feature Access
    # ──────────────────────────────────────────────────────────────────

    async def check_feature_access(self, user_id: int, feature: str) -> bool:
        """Check if user's subscription includes a feature."""
        subscription = await self.get_user_subscription(user_id)
        if not subscription:
            # Check if user is free tier (always allowed basic access)
            return feature in ["paper_trading", "basic_strategies"]

        # Check if subscription is still valid
        if subscription["status"] in ["canceled", "expired", "unpaid"]:
            return feature in ["paper_trading", "basic_strategies"]

        features = subscription.get("features", [])
        if isinstance(features, str):
            import json
            features = json.loads(features)
        return feature in features

    async def check_plan_limits(
        self,
        user_id: int,
        limit_type: str,
        current_count: int,
    ) -> bool:
        """Check if user is within plan limits."""
        subscription = await self.get_user_subscription(user_id)

        # Default free limits
        limits = {
            "devices": 1,
            "strategies": 2,
            "broker_accounts": 1,
            "backtests_per_day": 3,
            "api_calls_per_day": 100,
        }

        if subscription:
            plan_limits = {
                "devices": subscription.get("max_devices", 1),
                "strategies": subscription.get("max_strategies", 2),
            }
            limits.update(plan_limits)

        max_val = limits.get(limit_type, 999)
        return current_count < max_val

    # ──────────────────────────────────────────────────────────────────
    # License Keys
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def generate_license_key(tier: str = "pro") -> str:
        """Generate a formatted license key."""
        tier_prefix = {
            "free": "QF",
            "starter": "QS",
            "professional": "QP",
            "enterprise": "QE",
        }
        prefix = tier_prefix.get(tier, "QX")
        random_part = secrets.token_hex(8).upper()
        # Format: QP-XXXX-XXXX-XXXX-XXXX
        formatted = f"{prefix}-{random_part[:4]}-{random_part[4:8]}-{random_part[8:12]}-{random_part[12:16]}"
        return formatted

    # ──────────────────────────────────────────────────────────────────
    # Billing Portal
    # ──────────────────────────────────────────────────────────────────

    async def get_billing_portal_url(
        self,
        user_id: int,
        return_url: str,
    ) -> str:
        """Get Stripe Billing Portal URL for self-service."""
        subscription = await self.get_user_subscription(user_id)
        if not subscription or not subscription.get("stripe_customer_id"):
            raise ValueError("No billing account found")

        session = await stripe_service.create_billing_portal_session(
            stripe_customer_id=subscription["stripe_customer_id"],
            return_url=return_url,
        )
        return session.url

    async def get_payment_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get payment history for a user."""
        subscription = await self.get_user_subscription(user_id)
        if not subscription or not subscription.get("stripe_customer_id"):
            return []

        return await stripe_service.get_payment_history(
            stripe_customer_id=subscription["stripe_customer_id"],
        )


# Global instance
subscription_service = SubscriptionService()