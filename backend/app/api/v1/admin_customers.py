"""Admin Customer Management API.

Endpoints for managing customers, subscriptions, devices, and billing:
- List/search customers with filters
- View customer detail (subscription, devices, payments)
- Adjust subscriptions (upgrade, comp, pause)
- Remote device deactivation
- Refund processing
- Usage analytics overview
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_, desc

from app.core.database import async_session
from app.core.logging import logger
from app.models.user import User
from app.models.subscription import (
    CustomerSubscription, SubscriptionPlanConfig, Payment,
    Device, DeviceStatus, SubscriptionStatus, UsageRecord,
    PaymentStatus,
)
from app.services.subscription_service import subscription_service
from app.services.device_service import device_service
from app.services.stripe_service import stripe_service
from app.middleware.subscription_enforcement import (
    require_feature, require_plan_tier, enforce_rate_limit,
)
from app.api.v1.auth import get_current_admin_user


router = APIRouter(prefix="/admin/customers", tags=["Admin - Customers"])


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────

class CustomerListItem(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    plan_tier: Optional[str]
    subscription_status: Optional[str]
    created_at: datetime
    last_active: Optional[datetime]
    device_count: int = 0
    total_payments: float = 0


class CustomerDetail(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    license_key: Optional[str]
    subscription: Optional[dict]
    devices: List[dict]
    recent_payments: List[dict]
    usage_summary: Optional[dict]


class AdjustSubscriptionRequest(BaseModel):
    action: str = Field(..., description="upgrade, downgrade, comp, pause, cancel, reactivate")
    plan_id: Optional[int] = None
    reason: Optional[str] = None
    duration_days: Optional[int] = None


class RefundRequest(BaseModel):
    payment_id: int
    amount: Optional[float] = None
    reason: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# Customer List & Search
# ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[CustomerListItem])
async def list_customers(
    search: Optional[str] = Query(None, description="Search by email or name"),
    plan_tier: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_current_admin_user),
):
    """List all customers with search and filters."""
    async with async_session() as session:
        query = select(User).order_by(desc(User.created_at))

        # Search
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    User.email.ilike(search_pattern),
                    User.full_name.ilike(search_pattern),
                    User.license_key.ilike(search_pattern),
                )
            )

        # Pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await session.execute(query)
        users = result.scalars().all()

        customers = []
        for user in users:
            # Get subscription
            sub_result = await session.execute(
                select(CustomerSubscription, SubscriptionPlanConfig)
                .join(SubscriptionPlanConfig, CustomerSubscription.plan_id == SubscriptionPlanConfig.id, isouter=True)
                .where(CustomerSubscription.user_id == user.id)
                .order_by(desc(CustomerSubscription.created_at))
                .limit(1)
            )
            row = sub_result.first()
            sub = row[0] if row else None
            plan = row[1] if row else None

            # Filter by plan tier
            if plan_tier and (not plan or plan.plan_tier.value != plan_tier):
                continue

            # Filter by status
            if status_filter and (not sub or sub.status.value != status_filter):
                continue

            # Device count
            device_count_result = await session.execute(
                select(func.count(Device.id)).where(
                    Device.user_id == user.id,
                    Device.status == DeviceStatus.ACTIVE,
                )
            )
            device_count = device_count_result.scalar() or 0

            # Total payments
            total_payments_result = await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.user_id == user.id,
                    Payment.status == PaymentStatus.SUCCEEDED,
                )
            )
            total_payments = float(total_payments_result.scalar() or 0)

            customers.append(CustomerListItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                plan_tier=plan.plan_tier.value if plan else "free",
                subscription_status=sub.status.value if sub else None,
                created_at=user.created_at,
                last_active=user.last_login_at if hasattr(user, "last_login_at") else None,
                device_count=device_count,
                total_payments=total_payments,
            ))

        return customers


# ──────────────────────────────────────────────────────────────────────
# Customer Detail
# ──────────────────────────────────────────────────────────────────────

@router.get("/{customer_id}")
async def get_customer_detail(
    customer_id: int,
    admin: User = Depends(get_current_admin_user),
):
    """Get full customer detail including subscription, devices, payments."""
    async with async_session() as session:
        user = await session.get(User, customer_id)
        if not user:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Subscription
        sub_result = await session.execute(
            select(CustomerSubscription, SubscriptionPlanConfig)
            .join(SubscriptionPlanConfig, CustomerSubscription.plan_id == SubscriptionPlanConfig.id, isouter=True)
            .where(CustomerSubscription.user_id == user.id)
            .order_by(desc(CustomerSubscription.created_at))
            .limit(1)
        )
        row = sub_result.first()
        sub = row[0] if row else None
        plan = row[1] if row else None

        subscription_info = None
        if sub and plan:
            subscription_info = {
                "id": sub.id,
                "status": sub.status.value,
                "plan": plan.display_name,
                "plan_tier": plan.plan_tier.value,
                "billing_interval": sub.billing_interval.value,
                "price": float(sub.price_snapshot) if sub.price_snapshot else 0,
                "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                "cancel_at_period_end": sub.cancel_at_period_end,
                "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
                "stripe_subscription_id": sub.stripe_subscription_id,
                "stripe_customer_id": sub.stripe_customer_id,
            }

        # Devices
        devices_result = await session.execute(
            select(Device).where(Device.user_id == user.id).order_by(desc(Device.last_seen_at))
        )
        devices = [
            {
                "id": d.id,
                "fingerprint": d.device_fingerprint[:16] + "...",
                "name": d.device_name,
                "type": d.device_type,
                "os": d.os_info,
                "ip": d.ip_address,
                "status": d.status.value,
                "last_seen": d.last_seen_at.isoformat() if d.last_seen_at else None,
            }
            for d in devices_result.scalars().all()
        ]

        # Recent payments
        payments_result = await session.execute(
            select(Payment)
            .where(Payment.user_id == user.id)
            .order_by(desc(Payment.created_at))
            .limit(20)
        )
        payments = [
            {
                "id": p.id,
                "amount": float(p.amount),
                "currency": p.currency,
                "status": p.status.value,
                "description": p.description,
                "created_at": p.created_at.isoformat(),
                "stripe_invoice_id": p.stripe_invoice_id,
            }
            for p in payments_result.scalars().all()
        ]

        # Usage summary (last 30 days)
        usage_result = await session.execute(
            select(
                func.sum(UsageRecord.trades_executed).label("total_trades"),
                func.sum(UsageRecord.backtests_run).label("total_backtests"),
                func.sum(UsageRecord.api_calls).label("total_api_calls"),
                func.sum(UsageRecord.total_pnl).label("total_pnl"),
            ).where(
                UsageRecord.user_id == user.id,
                UsageRecord.usage_date >= datetime.now(timezone.utc) - timedelta(days=30),
            )
        )
        usage_row = usage_result.first()
        usage_summary = {
            "trades_30d": int(usage_row[0] or 0) if usage_row else 0,
            "backtests_30d": int(usage_row[1] or 0) if usage_row else 0,
            "api_calls_30d": int(usage_row[2] or 0) if usage_row else 0,
            "pnl_30d": float(usage_row[3] or 0) if usage_row else 0,
        }

        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "license_key": user.license_key,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "subscription": subscription_info,
            "devices": devices,
            "recent_payments": payments,
            "usage_summary": usage_summary,
        }


# ──────────────────────────────────────────────────────────────────────
# Adjust Subscription
# ──────────────────────────────────────────────────────────────────────

@router.post("/{customer_id}/adjust-subscription")
async def adjust_customer_subscription(
    customer_id: int,
    body: AdjustSubscriptionRequest,
    admin: User = Depends(get_current_admin_user),
):
    """Adjust a customer's subscription (admin action)."""
    async with async_session() as session:
        user = await session.get(User, customer_id)
        if not user:
            raise HTTPException(status_code=404, detail="Customer not found")

        action = body.action.lower()

        if action == "upgrade" and body.plan_id:
            result = await subscription_service.upgrade_subscription(customer_id, body.plan_id)
        elif action == "downgrade" and body.plan_id:
            result = await subscription_service.downgrade_subscription(customer_id, body.plan_id)
        elif action == "comp":
            # Complimentary subscription — create without payment
            if not body.plan_id:
                raise HTTPException(status_code=400, detail="plan_id required for comp action")
            result = await subscription_service.create_subscription(
                user_id=customer_id,
                plan_id=body.plan_id,
                billing_interval=BillingInterval.MONTHLY,
                start_trial=False,
            )
        elif action == "pause":
            sub_result = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == customer_id,
                    CustomerSubscription.status == SubscriptionStatus.ACTIVE,
                )
            )
            sub = sub_result.scalar_one_or_none()
            if not sub:
                raise HTTPException(status_code=404, detail="No active subscription")
            if sub.stripe_subscription_id:
                resume_at = None
                if body.duration_days:
                    resume_at = datetime.now(timezone.utc) + timedelta(days=body.duration_days)
                await stripe_service.pause_subscription(sub.stripe_subscription_id, resume_at)
            sub.status = SubscriptionStatus.PAUSED
            await session.commit()
            result = {"status": "paused", "reason": body.reason}
        elif action == "cancel":
            result = await subscription_service.cancel_subscription(
                customer_id, at_period_end=True, reason=body.reason
            )
        elif action == "reactivate":
            result = await subscription_service.reactivate_subscription(customer_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        logger.info(f"Admin {admin.id} adjusted subscription for user {customer_id}: {action}")
        return result


# ──────────────────────────────────────────────────────────────────────
# Remote Device Deactivation
# ──────────────────────────────────────────────────────────────────────

@router.post("/{customer_id}/deactivate-devices")
async def deactivate_customer_devices(
    customer_id: int,
    admin: User = Depends(get_current_admin_user),
):
    """Remotely deactivate all devices for a customer."""
    user_exists = await _check_user_exists(customer_id)
    if not user_exists:
        raise HTTPException(status_code=404, detail="Customer not found")

    result = await device_service.remote_deactivate_user(customer_id)
    logger.info(f"Admin {admin.id} deactivated all devices for user {customer_id}")
    return result


@router.post("/{customer_id}/devices/{device_id}/block")
async def block_customer_device(
    customer_id: int,
    device_id: int,
    reason: Optional[str] = None,
    admin: User = Depends(get_current_admin_user),
):
    """Block a specific device."""
    result = await device_service.block_device(customer_id, device_id, reason)
    logger.info(f"Admin {admin.id} blocked device {device_id} for user {customer_id}")
    return result


# ──────────────────────────────────────────────────────────────────────
# Refunds
# ──────────────────────────────────────────────────────────────────────

@router.post("/{customer_id}/refund")
async def process_refund(
    customer_id: int,
    body: RefundRequest,
    admin: User = Depends(get_current_admin_user),
):
    """Process a refund for a customer payment."""
    async with async_session() as session:
        payment = await session.get(Payment, body.payment_id)
        if not payment or payment.user_id != customer_id:
            raise HTTPException(status_code=404, detail="Payment not found")

        if payment.status == PaymentStatus.REFUNDED:
            raise HTTPException(status_code=400, detail="Payment already refunded")

        if not payment.stripe_payment_intent_id:
            raise HTTPException(status_code=400, detail="No Stripe payment intent")

        # Process refund via Stripe
        amount_cents = int((body.amount or float(payment.amount)) * 100)
        refund = await stripe_service.create_refund(
            payment_intent_id=payment.stripe_payment_intent_id,
            amount=amount_cents,
            reason=body.reason,
        )

        # Update local record
        payment.refunded_amount = body.amount or float(payment.amount)
        payment.refund_reason = body.reason
        if payment.refunded_amount >= float(payment.amount):
            payment.status = PaymentStatus.REFUNDED

        await session.commit()

        logger.info(f"Admin {admin.id} refunded ${body.amount or payment.amount} to user {customer_id}")

        return {
            "refund_id": refund.id,
            "amount": amount_cents / 100,
            "status": refund.status,
        }


# ──────────────────────────────────────────────────────────────────────
# Usage Analytics Overview
# ──────────────────────────────────────────────────────────────────────

@router.get("/analytics/overview")
async def get_analytics_overview(
    admin: User = Depends(get_current_admin_user),
):
    """Get platform-wide customer analytics overview."""
    async with async_session() as session:
        # Total customers
        total = await session.execute(select(func.count(User.id)))
        total_customers = total.scalar() or 0

        # Active subscribers
        active = await session.execute(
            select(func.count(CustomerSubscription.id)).where(
                CustomerSubscription.status.in_([
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING,
                ])
            )
        )
        active_subscribers = active.scalar() or 0

        # Plan distribution
        plan_dist = await session.execute(
            select(
                SubscriptionPlanConfig.plan_tier,
                func.count(CustomerSubscription.id),
            )
            .join(SubscriptionPlanConfig, CustomerSubscription.plan_id == SubscriptionPlanConfig.id)
            .where(CustomerSubscription.status.in_([
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIALING,
            ]))
            .group_by(SubscriptionPlanConfig.plan_tier)
        )
        plan_distribution = {row[0].value: row[1] for row in plan_dist.fetchall()}

        # Revenue (last 30 days)
        revenue = await session.execute(
            select(func.sum(Payment.amount)).where(
                Payment.status == PaymentStatus.SUCCEEDED,
                Payment.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
            )
        )
        revenue_30d = float(revenue.scalar() or 0)

        # MRR estimate
        mrr_result = await session.execute(
            select(func.sum(CustomerSubscription.price_snapshot)).where(
                CustomerSubscription.status == SubscriptionStatus.ACTIVE,
                CustomerSubscription.billing_interval == "monthly",
            )
        )
        mrr = float(mrr_result.scalar() or 0)

        # Add annual/12
        arr_result = await session.execute(
            select(func.sum(CustomerSubscription.price_snapshot)).where(
                CustomerSubscription.status == SubscriptionStatus.ACTIVE,
                CustomerSubscription.billing_interval == "annual",
            )
        )
        arr = float(arr_result.scalar() or 0)
        mrr += arr / 12

        # Active devices
        device_count = await session.execute(
            select(func.count(Device.id)).where(Device.status == DeviceStatus.ACTIVE)
        )
        active_devices = device_count.scalar() or 0

        # Trials
        trial_count = await session.execute(
            select(func.count(CustomerSubscription.id)).where(
                CustomerSubscription.status == SubscriptionStatus.TRIALING
            )
        )
        active_trials = trial_count.scalar() or 0

        # Churn (canceled in last 30 days)
        churn = await session.execute(
            select(func.count(CustomerSubscription.id)).where(
                CustomerSubscription.status == SubscriptionStatus.CANCELED,
                CustomerSubscription.canceled_at >= datetime.now(timezone.utc) - timedelta(days=30),
            )
        )
        churned_30d = churn.scalar() or 0

        return {
            "total_customers": total_customers,
            "active_subscribers": active_subscribers,
            "plan_distribution": plan_distribution,
            "revenue_30d": revenue_30d,
            "mrr_estimate": round(mrr, 2),
            "active_devices": active_devices,
            "active_trials": active_trials,
            "churned_30d": churned_30d,
        }


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

async def _check_user_exists(user_id: int) -> bool:
    async with async_session() as session:
        user = await session.get(User, user_id)
        return user is not None