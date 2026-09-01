"""Subscription, billing, and device models for commercial SaaS platform."""
import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, BigInteger,
    String, Text, Numeric, JSON, Index, UniqueConstraint, Float
)
from sqlalchemy.orm import relationship

from app.core.database import Base


# ──────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────

class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    PAUSED = "paused"
    EXPIRED = "expired"


class BillingInterval(str, enum.Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    LIFETIME = "lifetime"


class PlanTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class DeviceStatus(str, enum.Enum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    BLOCKED = "blocked"


class WebhookEventType(str, enum.Enum):
    # Stripe events
    CHECKOUT_COMPLETED = "checkout.session.completed"
    INVOICE_PAID = "invoice.paid"
    INVOICE_PAYMENT_FAILED = "invoice.payment_failed"
    SUBSCRIPTION_UPDATED = "customer.subscription.updated"
    SUBSCRIPTION_DELETED = "customer.subscription.deleted"
    CHARGE_REFUNDED = "charge.refunded"
    DISPUTE_CREATED = "charge.dispute.created"


# ──────────────────────────────────────────────────────────────────────
# Subscription Plans (catalog)
# ──────────────────────────────────────────────────────────────────────

class SubscriptionPlanConfig(Base):
    """Plan catalog — defines available plans, prices, and limits."""
    __tablename__ = "subscription_plans"
    __table_args__ = (
        UniqueConstraint("plan_tier", "billing_interval", name="uq_plan_tier_interval"),
        Index("idx_plan_active", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    plan_tier = Column(Enum(PlanTier), nullable=False)
    billing_interval = Column(Enum(BillingInterval), nullable=False)

    # Pricing
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    stripe_price_id = Column(String(255), nullable=True, unique=True)

    # Limits
    max_devices = Column(Integer, default=1)
    max_strategies = Column(Integer, default=3)
    max_broker_accounts = Column(Integer, default=1)
    max_backtests_per_day = Column(Integer, default=10)
    max_api_calls_per_day = Column(Integer, default=1000)

    # Features (JSON list of feature flags)
    features = Column(JSON, default=list)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Trial
    trial_days = Column(Integer, default=0)

    # Meta
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ──────────────────────────────────────────────────────────────────────
# Customer Subscription
# ──────────────────────────────────────────────────────────────────────

class CustomerSubscription(Base):
    """Active subscription for a customer."""
    __tablename__ = "customer_subscriptions"
    __table_args__ = (
        Index("idx_sub_user", "user_id"),
        Index("idx_sub_status", "status"),
        Index("idx_sub_stripe", "stripe_subscription_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)

    # Stripe integration
    stripe_subscription_id = Column(String(255), nullable=True, unique=True)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_price_id = Column(String(255), nullable=True)

    # Status
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.TRIALING)
    billing_interval = Column(Enum(BillingInterval), default=BillingInterval.MONTHLY)

    # Trial
    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    is_trial_used = Column(Boolean, default=False)

    # Dates
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    ended_at = Column(DateTime, nullable=True)

    # Pricing snapshot
    price_snapshot = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="USD")

    # Metadata
    metadata_json = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    plan = relationship("SubscriptionPlanConfig")
    payments = relationship("Payment", back_populates="subscription", lazy="selectin")


# ──────────────────────────────────────────────────────────────────────
# Payments
# ──────────────────────────────────────────────────────────────────────

class Payment(Base):
    """Payment records linked to subscriptions."""
    __tablename__ = "payments"
    __table_args__ = (
        Index("idx_payment_user", "user_id"),
        Index("idx_payment_sub", "subscription_id"),
        Index("idx_payment_stripe", "stripe_payment_intent_id"),
        Index("idx_payment_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("customer_subscriptions.id", ondelete="SET NULL"), nullable=True)

    # Stripe
    stripe_payment_intent_id = Column(String(255), nullable=True, unique=True)
    stripe_invoice_id = Column(String(255), nullable=True)
    stripe_charge_id = Column(String(255), nullable=True)

    # Amount
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)

    # Description
    description = Column(String(500), nullable=True)
    payment_type = Column(String(50), default="subscription")  # subscription, upgrade, one_time

    # Refund
    refunded_amount = Column(Numeric(10, 2), default=0)
    refund_reason = Column(Text, nullable=True)

    # Metadata
    metadata_json = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    subscription = relationship("CustomerSubscription", back_populates="payments")


# ──────────────────────────────────────────────────────────────────────
# Device Registrations
# ──────────────────────────────────────────────────────────────────────

class Device(Base):
    """Device registrations for license activation limits."""
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("user_id", "device_fingerprint", name="uq_user_device"),
        Index("idx_device_user", "user_id"),
        Index("idx_device_fingerprint", "device_fingerprint"),
        Index("idx_device_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Device identification
    device_fingerprint = Column(String(512), nullable=False)
    device_name = Column(String(255), nullable=True)
    device_type = Column(String(50), nullable=True)  # desktop, mobile, server
    os_info = Column(String(255), nullable=True)
    app_version = Column(String(50), nullable=True)

    # Network
    ip_address = Column(String(50), nullable=True)
    geo_location = Column(String(100), nullable=True)

    # Status
    status = Column(Enum(DeviceStatus), default=DeviceStatus.ACTIVE)
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    activated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    deactivated_at = Column(DateTime, nullable=True)

    # Metadata
    metadata_json = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User")


# ──────────────────────────────────────────────────────────────────────
# License Activation Records
# ──────────────────────────────────────────────────────────────────────

class LicenseActivation(Base):
    """License activation history."""
    __tablename__ = "license_activations"
    __table_args__ = (
        Index("idx_activation_user", "user_id"),
        Index("idx_activation_license", "license_key"),
        Index("idx_activation_device", "device_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    license_key = Column(String(255), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)

    # Activation details
    activation_token = Column(String(512), nullable=True, unique=True)
    ip_address = Column(String(50), nullable=True)
    activated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
    deactivated_at = Column(DateTime, nullable=True)

    # Heartbeat
    last_heartbeat = Column(DateTime, nullable=True)
    heartbeat_count = Column(Integer, default=0)

    # Metadata
    metadata_json = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ──────────────────────────────────────────────────────────────────────
# Webhook Event Log
# ──────────────────────────────────────────────────────────────────────

class WebhookEvent(Base):
    """Stripe webhook event log for idempotency and audit."""
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("stripe_event_id", name="uq_stripe_event"),
        Index("idx_webhook_type", "event_type"),
        Index("idx_webhook_processed", "processed"),
    )

    id = Column(Integer, primary_key=True, index=True)
    stripe_event_id = Column(String(255), nullable=False, unique=True)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False)

    # Processing
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ──────────────────────────────────────────────────────────────────────
# Usage Tracking (daily aggregates)
# ──────────────────────────────────────────────────────────────────────

class UsageRecord(Base):
    """Daily usage tracking per customer for analytics and limits."""
    __tablename__ = "usage_records"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uq_user_usage_date"),
        Index("idx_usage_user_date", "user_id", "usage_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    usage_date = Column(DateTime, nullable=False)

    # Counters
    trades_executed = Column(Integer, default=0)
    strategies_active = Column(Integer, default=0)
    backtests_run = Column(Integer, default=0)
    api_calls = Column(BigInteger, default=0)
    signals_generated = Column(Integer, default=0)
    active_devices = Column(Integer, default=0)

    # Computed
    total_pnl = Column(Numeric(15, 2), default=0)
    total_volume = Column(Numeric(15, 2), default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))