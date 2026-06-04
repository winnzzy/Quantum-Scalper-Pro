"""Customer Self-Service Portal API.

Endpoints for customers to manage their own:
- Subscription (view, upgrade, downgrade, cancel)
- Devices (list, deactivate)
- Payments (history, invoices)
- Billing portal redirect
- License key retrieval
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.database import async_session
from app.core.logging import logger
from app.models.user import User
from app.models.subscription import BillingInterval
from app.services.subscription_service import subscription_service
from app.services.device_service import device_service
from app.middleware.subscription_enforcement import (
    get_active_subscription, require_feature,
)


router = APIRouter(prefix="/subscription", tags=["Customer Portal"])


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────

class CreateCheckoutRequest(BaseModel):
    plan_id: int
    success_url: str = "https://app.quantumscalperpro.com/subscription/success"
    cancel_url: str = "https://app.quantumscalperpro.com/pricing"


class UpgradeRequest(BaseModel):
    plan_id: int


class CancelRequest(BaseModel):
    reason: Optional[str] = None
    feedback: Optional[str] = None
    at_period_end: bool = True


class ActivateLicenseRequest(BaseModel):
    license_key: str
    device_fingerprint: str


class DeactivateDeviceRequest(BaseModel):
    device_id: int


# ──────────────────────────────────────────────────────────────────────
# Plans
# ──────────────────────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans():
    """List all available subscription plans (public)."""
    plans = await subscription_service.get_plans(active_only=True)
    return {"plans": plans}


# ──────────────────────────────────────────────────────────────────────
# Current Subscription
# ──────────────────────────────────────────────────────────────────────

@router.get("/current")
async def get_current_subscription(
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Get current user's subscription details."""
    subscription = await subscription_service.get_user_subscription(request.state.user.id)
    if not subscription:
        return {
            "has_subscription": False,
            "plan": "free",
            "features": ["paper_trading", "basic_strategies"],
        }

    return {
        "has_subscription": True,
        **subscription,
    }


# ──────────────────────────────────────────────────────────────────────
# Checkout
# ──────────────────────────────────────────────────────────────────────

@router.post("/checkout")
async def create_checkout(
    body: CreateCheckoutRequest,
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Create Stripe Checkout session for subscription purchase."""
    try:
        result = await subscription_service.create_checkout(
            user_id=request.state.user.id,
            plan_id=body.plan_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────────────────────────────
# Plan Changes
# ──────────────────────────────────────────────────────────────────────

@router.post("/upgrade")
async def upgrade_plan(
    body: UpgradeRequest,
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Upgrade subscription to a higher plan."""
    try:
        result = await subscription_service.upgrade_subscription(
            user_id=request.state.user.id,
            new_plan_id=body.plan_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/downgrade")
async def downgrade_plan(
    body: UpgradeRequest,
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Downgrade subscription at end of current period."""
    try:
        result = await subscription_service.downgrade_subscription(
            user_id=request.state.user.id,
            new_plan_id=body.plan_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cancel")
async def cancel_subscription(
    body: CancelRequest,
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Cancel current subscription."""
    try:
        result = await subscription_service.cancel_subscription(
            user_id=request.state.user.id,
            at_period_end=body.at_period_end,
            reason=body.reason,
            feedback=body.feedback,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reactivate")
async def reactivate_subscription(
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Reactivate a subscription set to cancel at period end."""
    try:
        result = await subscription_service.reactivate_subscription(
            user_id=request.state.user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────────────────────────────
# Trials
# ──────────────────────────────────────────────────────────────────────

@router.post("/trial")
async def start_trial(
    plan_tier: str = "professional",
    request: Request = None,
):
    """Start a free trial."""
    from app.models.subscription import PlanTier
    from app.api.v1.auth import get_current_user

    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tier_map = {
        "starter": PlanTier.STARTER,
        "professional": PlanTier.PROFESSIONAL,
        "enterprise": PlanTier.ENTERPRISE,
    }
    tier = tier_map.get(plan_tier, PlanTier.PROFESSIONAL)

    try:
        result = await subscription_service.start_trial(
            user_id=user.id,
            plan_tier=tier,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────────────────────────────
# Billing Portal
# ──────────────────────────────────────────────────────────────────────

@router.get("/billing-portal")
async def get_billing_portal(
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Get Stripe Billing Portal URL for self-service."""
    try:
        return_url = str(request.base_url) + "subscription"
        url = await subscription_service.get_billing_portal_url(
            user_id=request.state.user.id,
            return_url=return_url,
        )
        return {"url": url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────────────────────────────
# Payment History
# ──────────────────────────────────────────────────────────────────────

@router.get("/payments")
async def get_payment_history(
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Get payment history."""
    payments = await subscription_service.get_payment_history(
        user_id=request.state.user.id,
    )
    return {"payments": payments}


# ──────────────────────────────────────────────────────────────────────
# Device Management
# ──────────────────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """List user's registered devices."""
    devices = await device_service.list_user_devices(
        user_id=request.state.user.id,
    )
    return {"devices": devices}


@router.post("/devices/deactivate")
async def deactivate_device(
    body: DeactivateDeviceRequest,
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Deactivate a device (frees up a device slot)."""
    try:
        result = await device_service.deactivate_device(
            user_id=request.state.user.id,
            device_id=body.device_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────────────────────────────
# License Activation (for desktop client)
# ──────────────────────────────────────────────────────────────────────

@router.post("/activate")
async def activate_license(
    body: ActivateLicenseRequest,
    request: Request,
):
    """Activate license key on a device.

    Used by the desktop trading client to activate the license.
    Requires authentication.
    """
    from app.api.v1.auth import get_current_user

    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    ip = request.client.host if request.client else None

    try:
        result = await device_service.activate_license(
            user_id=user.id,
            license_key=body.license_key,
            device_fingerprint=body.device_fingerprint,
            ip_address=ip,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deactivate")
async def deactivate_license(
    activation_token: str,
    request: Request,
):
    """Deactivate a license activation."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        result = await device_service.deactivate_license(
            user_id=user.id,
            activation_token=activation_token,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/heartbeat")
async def license_heartbeat(
    activation_token: str,
    device_fingerprint: Optional[str] = None,
):
    """Heartbeat endpoint for license validation.

    Called periodically by the desktop client to keep activation alive.
    No authentication required — token itself is the credential.
    """
    result = await device_service.heartbeat(
        activation_token=activation_token,
        device_fingerprint=device_fingerprint,
    )

    if not result.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "activation_invalid",
                "reason": result.get("reason", "Unknown"),
                "reactivate_url": "/subscription/activate",
            },
        )

    return result


@router.get("/license-key")
async def get_license_key(
    request: Request,
    user: User = Depends(get_active_subscription),
):
    """Get user's license key."""
    from sqlalchemy import select
    from app.models.user import User as UserModel

    from app.core.database import async_session

    async with async_session() as session:
        u = await session.get(UserModel, request.state.user.id)
        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "license_key": u.license_key,
            "subscription_plan": u.subscription_plan.value if u.subscription_plan else "free",
        }