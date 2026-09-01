"""Customer-facing subscription and Stripe billing endpoints."""
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, HttpUrl

from app.auth.service import get_current_active_user
from app.core.config import settings
from app.models.user import User
from app.services.stripe_service import stripe_service
from app.services.subscription_service import subscription_service


router = APIRouter()


class CheckoutRequest(BaseModel):
    plan_id: int
    success_url: Optional[HttpUrl] = None
    cancel_url: Optional[HttpUrl] = None


class PortalRequest(BaseModel):
    return_url: Optional[HttpUrl] = None


class CancelRequest(BaseModel):
    at_period_end: bool = True
    reason: Optional[str] = None


@router.get("/plans")
async def list_plans():
    """Return the active public plan catalog."""
    return {"plans": await subscription_service.get_plans(active_only=True)}


@router.get("/subscription")
async def get_subscription(
    current_user: User = Depends(get_current_active_user),
):
    """Return the signed-in user's current subscription."""
    subscription = await subscription_service.get_user_subscription(current_user.id)
    return {"subscription": subscription}


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Create a hosted Stripe Checkout session."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing is not configured")

    success_url = str(body.success_url or f"{settings.FRONTEND_URL}/billing?checkout=success")
    cancel_url = str(body.cancel_url or f"{settings.FRONTEND_URL}/billing?checkout=cancelled")
    try:
        return await subscription_service.create_checkout(
            user_id=current_user.id,
            plan_id=body.plan_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except (ValueError, stripe.StripeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/portal")
async def create_portal(
    body: PortalRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Create a Stripe self-service billing portal session."""
    subscription = await subscription_service.get_user_subscription(current_user.id)
    customer_id = subscription.get("stripe_customer_id") if subscription else None
    if not customer_id:
        raise HTTPException(status_code=404, detail="No billing customer found")

    try:
        session = await stripe_service.create_billing_portal_session(
            stripe_customer_id=customer_id,
            return_url=str(body.return_url or f"{settings.FRONTEND_URL}/billing"),
        )
        return {"portal_url": session.url}
    except stripe.StripeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel")
async def cancel_subscription(
    body: CancelRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Cancel the signed-in user's subscription."""
    try:
        return await subscription_service.cancel_subscription(
            user_id=current_user.id,
            at_period_end=body.at_period_end,
            reason=body.reason,
        )
    except (ValueError, stripe.StripeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
):
    """Verify and process Stripe webhook events idempotently."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")

    payload = await request.body()
    try:
        event = stripe_service.verify_webhook_signature(payload, stripe_signature)
        return await stripe_service.process_webhook_event(event)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc
