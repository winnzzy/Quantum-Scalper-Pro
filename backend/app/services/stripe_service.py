"""Stripe billing integration service.

Handles all Stripe API interactions for subscription lifecycle:
- Customer creation and management
- Checkout session creation
- Subscription CRUD (create, update, cancel, reactivate)
- Webhook event processing
- Payment and refund handling
- Invoice management

Designed for thousands of concurrent customers with idempotent operations.
"""
import stripe
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal

from app.core.config import settings
from app.core.logging import logger
from app.core.database import async_session


# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = "2024-06-20"


class StripeService:
    """Stripe billing integration."""

    # ──────────────────────────────────────────────────────────────────
    # Customer Management
    # ──────────────────────────────────────────────────────────────────

    async def get_or_create_customer(
        self,
        user_id: int,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> stripe.Customer:
        """Get existing or create new Stripe customer."""
        try:
            # Search for existing customer by metadata
            customers = stripe.Customer.list(
                email=email,
                limit=1,
            )
            if customers.data:
                customer = customers.data[0]
                # Update metadata if needed
                if metadata:
                    stripe.Customer.modify(
                        customer.id,
                        metadata={**customer.metadata, **metadata, "user_id": str(user_id)},
                    )
                return customer

            # Create new customer
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={
                    "user_id": str(user_id),
                    "source": "quantum_scalper_pro",
                    **(metadata or {}),
                },
            )
            logger.info(f"Created Stripe customer {customer.id} for user {user_id}")
            return customer

        except stripe.StripeError as e:
            logger.error(f"Stripe customer error: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────
    # Checkout Sessions
    # ──────────────────────────────────────────────────────────────────

    async def create_checkout_session(
        self,
        stripe_customer_id: str,
        stripe_price_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: int = 0,
        metadata: Optional[Dict[str, str]] = None,
    ) -> stripe.checkout.Session:
        """Create Stripe Checkout session for new subscription."""
        try:
            session_params = {
                "customer": stripe_customer_id,
                "mode": "subscription",
                "payment_method_types": ["card"],
                "line_items": [{"price": stripe_price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata or {},
                "subscription_data": {
                    "metadata": metadata or {},
                },
            }

            if trial_days > 0:
                session_params["subscription_data"]["trial_period_days"] = trial_days

            session = stripe.checkout.Session.create(**session_params)
            logger.info(f"Created checkout session {session.id} for customer {stripe_customer_id}")
            return session

        except stripe.StripeError as e:
            logger.error(f"Checkout session error: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────
    # Subscription Management
    # ──────────────────────────────────────────────────────────────────

    async def create_subscription(
        self,
        stripe_customer_id: str,
        stripe_price_id: str,
        trial_days: int = 0,
        metadata: Optional[Dict[str, str]] = None,
    ) -> stripe.Subscription:
        """Create a subscription directly (without checkout)."""
        try:
            sub_params = {
                "customer": stripe_customer_id,
                "items": [{"price": stripe_price_id}],
                "metadata": metadata or {},
                "payment_behavior": "default_incomplete",
                "expand": ["latest_invoice.payment_intent"],
            }

            if trial_days > 0:
                sub_params["trial_period_days"] = trial_days

            subscription = stripe.Subscription.create(**sub_params)
            logger.info(f"Created subscription {subscription.id} for customer {stripe_customer_id}")
            return subscription

        except stripe.StripeError as e:
            logger.error(f"Subscription creation error: {e}")
            raise

    async def update_subscription(
        self,
        stripe_subscription_id: str,
        new_price_id: str,
        proration_behavior: str = "create_prorations",
        metadata: Optional[Dict[str, str]] = None,
    ) -> stripe.Subscription:
        """Update subscription plan (upgrade/downgrade)."""
        try:
            # Get current subscription
            subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            current_item = subscription["items"]["data"][0]

            update_params = {
                "items": [{
                    "id": current_item["id"],
                    "price": new_price_id,
                }],
                "proration_behavior": proration_behavior,
                "metadata": {**subscription.metadata, **(metadata or {})},
            }

            updated = stripe.Subscription.modify(
                stripe_subscription_id,
                **update_params,
            )
            logger.info(f"Updated subscription {stripe_subscription_id} to price {new_price_id}")
            return updated

        except stripe.StripeError as e:
            logger.error(f"Subscription update error: {e}")
            raise

    async def cancel_subscription(
        self,
        stripe_subscription_id: str,
        at_period_end: bool = True,
        cancellation_reason: Optional[str] = None,
    ) -> stripe.Subscription:
        """Cancel subscription."""
        try:
            if at_period_end:
                subscription = stripe.Subscription.modify(
                    stripe_subscription_id,
                    cancel_at_period_end=True,
                    metadata={"cancellation_reason": cancellation_reason or ""},
                )
                logger.info(f"Subscription {stripe_subscription_id} set to cancel at period end")
            else:
                subscription = stripe.Subscription.delete(stripe_subscription_id)
                logger.info(f"Subscription {stripe_subscription_id} canceled immediately")

            return subscription

        except stripe.StripeError as e:
            logger.error(f"Subscription cancellation error: {e}")
            raise

    async def reactivate_subscription(
        self,
        stripe_subscription_id: str,
    ) -> stripe.Subscription:
        """Reactivate a subscription that was set to cancel at period end."""
        try:
            subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=False,
            )
            logger.info(f"Subscription {stripe_subscription_id} reactivated")
            return subscription

        except stripe.StripeError as e:
            logger.error(f"Subscription reactivation error: {e}")
            raise

    async def pause_subscription(
        self,
        stripe_subscription_id: str,
        resume_at: Optional[datetime] = None,
    ) -> stripe.Subscription:
        """Pause subscription (collections)."""
        try:
            pause_params = {
                "pause_collection": {"behavior": "void"},
            }
            if resume_at:
                pause_params["pause_collection"]["resumes_at"] = int(resume_at.timestamp())

            subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                **pause_params,
            )
            logger.info(f"Subscription {stripe_subscription_id} paused")
            return subscription

        except stripe.StripeError as e:
            logger.error(f"Subscription pause error: {e}")
            raise

    async def resume_subscription(
        self,
        stripe_subscription_id: str,
    ) -> stripe.Subscription:
        """Resume a paused subscription."""
        try:
            subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                pause_collection="",
            )
            logger.info(f"Subscription {stripe_subscription_id} resumed")
            return subscription

        except stripe.StripeError as e:
            logger.error(f"Subscription resume error: {e}")
            raise

    async def get_subscription(
        self,
        stripe_subscription_id: str,
    ) -> stripe.Subscription:
        """Retrieve subscription details."""
        return stripe.Subscription.retrieve(
            stripe_subscription_id,
            expand=["latest_invoice", "default_payment_method"],
        )

    async def list_customer_subscriptions(
        self,
        stripe_customer_id: str,
        status: Optional[str] = None,
    ) -> List[stripe.Subscription]:
        """List all subscriptions for a customer."""
        params = {"customer": stripe_customer_id, "limit": 100}
        if status:
            params["status"] = status
        result = stripe.Subscription.list(**params)
        return result.data

    # ──────────────────────────────────────────────────────────────────
    # Portal / Self-Service
    # ──────────────────────────────────────────────────────────────────

    async def create_billing_portal_session(
        self,
        stripe_customer_id: str,
        return_url: str,
    ) -> stripe.billing_portal.Session:
        """Create Stripe Billing Portal session for self-service."""
        try:
            session = stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=return_url,
            )
            return session

        except stripe.StripeError as e:
            logger.error(f"Billing portal error: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────
    # Payments & Invoices
    # ──────────────────────────────────────────────────────────────────

    async def get_payment_history(
        self,
        stripe_customer_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get payment history for a customer."""
        try:
            charges = stripe.Charge.list(
                customer=stripe_customer_id,
                limit=limit,
            )
            return [
                {
                    "id": c.id,
                    "amount": c.amount / 100,
                    "currency": c.currency,
                    "status": c.status,
                    "description": c.description,
                    "created": datetime.fromtimestamp(c.created, tz=timezone.utc),
                    "invoice_id": c.invoice,
                    "payment_intent_id": c.payment_intent,
                }
                for c in charges.data
            ]
        except stripe.StripeError as e:
            logger.error(f"Payment history error: {e}")
            raise

    async def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> stripe.Refund:
        """Create a refund."""
        try:
            refund_params = {"payment_intent": payment_intent_id}
            if amount:
                refund_params["amount"] = amount
            if reason:
                refund_params["reason"] = reason

            refund = stripe.Refund.create(**refund_params)
            logger.info(f"Created refund {refund.id} for {payment_intent_id}")
            return refund

        except stripe.StripeError as e:
            logger.error(f"Refund error: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────
    # Webhook Verification
    # ──────────────────────────────────────────────────────────────────

    def verify_webhook_signature(
        self,
        payload: bytes,
        sig_header: str,
    ) -> stripe.Event:
        """Verify Stripe webhook signature and return event."""
        try:
            event = stripe.Webhook.construct_event(
                payload,
                sig_header,
                settings.STRIPE_WEBHOOK_SECRET,
            )
            return event
        except stripe.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────
    # Webhook Event Processing
    # ──────────────────────────────────────────────────────────────────

    async def process_webhook_event(self, event: stripe.Event) -> Dict[str, Any]:
        """Process a verified Stripe webhook event."""
        from app.models.subscription import (
            WebhookEvent, CustomerSubscription, SubscriptionStatus,
            Payment, PaymentStatus,
        )

        event_type = event["type"]
        data = event["data"]["object"]

        logger.info(f"Processing webhook event: {event_type} ({event['id']})")

        async with async_session() as session:
            # Idempotency check
            from sqlalchemy import select
            existing = await session.execute(
                select(WebhookEvent).where(WebhookEvent.stripe_event_id == event["id"])
            )
            if existing.scalar_one_or_none():
                logger.info(f"Event {event['id']} already processed, skipping")
                return {"status": "already_processed"}

            # Log event
            webhook_event = WebhookEvent(
                stripe_event_id=event["id"],
                event_type=event_type,
                payload=event["data"],
            )
            session.add(webhook_event)

            result = {"status": "processed", "event_type": event_type}

            try:
                if event_type == "checkout.session.completed":
                    result["details"] = await self._handle_checkout_completed(session, data)

                elif event_type == "invoice.paid":
                    result["details"] = await self._handle_invoice_paid(session, data)

                elif event_type == "invoice.payment_failed":
                    result["details"] = await self._handle_invoice_payment_failed(session, data)

                elif event_type == "customer.subscription.updated":
                    result["details"] = await self._handle_subscription_updated(session, data)

                elif event_type == "customer.subscription.deleted":
                    result["details"] = await self._handle_subscription_deleted(session, data)

                elif event_type == "charge.refunded":
                    result["details"] = await self._handle_charge_refunded(session, data)

                elif event_type == "charge.dispute.created":
                    result["details"] = await self._handle_dispute_created(session, data)

                else:
                    logger.info(f"Unhandled event type: {event_type}")
                    result["details"] = "unhandled"

                webhook_event.processed = True
                webhook_event.processed_at = datetime.now(timezone.utc)

            except Exception as e:
                webhook_event.error_message = str(e)
                webhook_event.retry_count += 1
                logger.error(f"Error processing webhook {event_type}: {e}")
                result["status"] = "error"
                result["error"] = str(e)

            await session.commit()
            return result

    async def _handle_checkout_completed(self, session, data: Dict) -> str:
        """Handle checkout.session.completed event."""
        from sqlalchemy import select
        from app.models.subscription import CustomerSubscription, SubscriptionStatus

        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")

        if not user_id or not subscription_id:
            return "missing_metadata"

        # Update subscription with Stripe IDs
        sub = await session.execute(
            select(CustomerSubscription).where(
                CustomerSubscription.user_id == int(user_id),
                CustomerSubscription.status == SubscriptionStatus.TRIALING,
            )
        )
        subscription = sub.scalar_one_or_none()
        if subscription:
            subscription.stripe_subscription_id = subscription_id
            subscription.stripe_customer_id = customer_id
            subscription.status = SubscriptionStatus.ACTIVE
            logger.info(f"Activated subscription for user {user_id}")

        return "activated"

    async def _handle_invoice_paid(self, session, data: Dict) -> str:
        """Handle invoice.paid event."""
        from sqlalchemy import select
        from app.models.subscription import CustomerSubscription, Payment, PaymentStatus, SubscriptionStatus

        subscription_id = data.get("subscription")
        if not subscription_id:
            return "no_subscription"

        sub = await session.execute(
            select(CustomerSubscription).where(
                CustomerSubscription.stripe_subscription_id == subscription_id
            )
        )
        subscription = sub.scalar_one_or_none()
        if subscription:
            subscription.status = SubscriptionStatus.ACTIVE

            # Record payment
            payment = Payment(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                stripe_payment_intent_id=data.get("payment_intent"),
                stripe_invoice_id=data.get("id"),
                amount=Decimal(str(data.get("amount_paid", 0) / 100)),
                currency=data.get("currency", "usd").upper(),
                status=PaymentStatus.SUCCEEDED,
                description=data.get("description", "Subscription payment"),
                payment_type="subscription",
            )
            session.add(payment)

            # Update period dates
            if data.get("period_start"):
                subscription.current_period_start = datetime.fromtimestamp(
                    data["period_start"], tz=timezone.utc
                )
            if data.get("period_end"):
                subscription.current_period_end = datetime.fromtimestamp(
                    data["period_end"], tz=timezone.utc
                )

        return "payment_recorded"

    async def _handle_invoice_payment_failed(self, session, data: Dict) -> str:
        """Handle invoice.payment_failed event."""
        from sqlalchemy import select
        from app.models.subscription import CustomerSubscription, SubscriptionStatus

        subscription_id = data.get("subscription")
        if not subscription_id:
            return "no_subscription"

        sub = await session.execute(
            select(CustomerSubscription).where(
                CustomerSubscription.stripe_subscription_id == subscription_id
            )
        )
        subscription = sub.scalar_one_or_none()
        if subscription:
            subscription.status = SubscriptionStatus.PAST_DUE
            logger.warning(f"Payment failed for subscription {subscription_id}")

        return "marked_past_due"

    async def _handle_subscription_updated(self, session, data: Dict) -> str:
        """Handle customer.subscription.updated event."""
        from sqlalchemy import select
        from app.models.subscription import CustomerSubscription, SubscriptionStatus

        stripe_sub_id = data.get("id")
        stripe_status = data.get("status")

        sub = await session.execute(
            select(CustomerSubscription).where(
                CustomerSubscription.stripe_subscription_id == stripe_sub_id
            )
        )
        subscription = sub.scalar_one_or_none()
        if subscription:
            # Map Stripe status to our status
            status_map = {
                "trialing": SubscriptionStatus.TRIALING,
                "active": SubscriptionStatus.ACTIVE,
                "past_due": SubscriptionStatus.PAST_DUE,
                "canceled": SubscriptionStatus.CANCELED,
                "unpaid": SubscriptionStatus.UNPAID,
                "paused": SubscriptionStatus.PAUSED,
            }
            subscription.status = status_map.get(stripe_status, subscription.status)

            # Update cancellation flags
            subscription.cancel_at_period_end = data.get("cancel_at_period_end", False)
            if data.get("canceled_at"):
                subscription.canceled_at = datetime.fromtimestamp(
                    data["canceled_at"], tz=timezone.utc
                )

            # Update price
            items = data.get("items", {}).get("data", [])
            if items:
                subscription.stripe_price_id = items[0].get("price", {}).get("id")

        return "subscription_synced"

    async def _handle_subscription_deleted(self, session, data: Dict) -> str:
        """Handle customer.subscription.deleted event."""
        from sqlalchemy import select
        from app.models.subscription import CustomerSubscription, SubscriptionStatus

        stripe_sub_id = data.get("id")

        sub = await session.execute(
            select(CustomerSubscription).where(
                CustomerSubscription.stripe_subscription_id == stripe_sub_id
            )
        )
        subscription = sub.scalar_one_or_none()
        if subscription:
            subscription.status = SubscriptionStatus.CANCELED
            subscription.ended_at = datetime.now(timezone.utc)
            logger.info(f"Subscription {stripe_sub_id} deleted/ended")

        return "subscription_canceled"

    async def _handle_charge_refunded(self, session, data: Dict) -> str:
        """Handle charge.refunded event."""
        from sqlalchemy import select
        from app.models.subscription import Payment, PaymentStatus

        pi_id = data.get("payment_intent")
        if not pi_id:
            return "no_payment_intent"

        payment_result = await session.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == pi_id)
        )
        payment = payment_result.scalar_one_or_none()
        if payment:
            payment.refunded_amount = Decimal(str(data.get("amount_refunded", 0) / 100))
            if payment.refunded_amount >= payment.amount:
                payment.status = PaymentStatus.REFUNDED
            payment.refund_reason = data.get("reason", "")

        return "refund_recorded"

    async def _handle_dispute_created(self, session, data: Dict) -> str:
        """Handle charge.dispute.created event."""
        logger.warning(f"Dispute created: {data.get('id')} - {data.get('reason')}")
        # In production: alert admin, pause subscription, collect evidence
        return "dispute_logged"


# Global instance
stripe_service = StripeService()