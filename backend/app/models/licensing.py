"""Licensing and subscription models."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, String,
    Text, Numeric, JSON, Index, UniqueConstraint, BigInteger
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class LicenseStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    PENDING = "pending"


class License(Base):
    __tablename__ = "licenses"
    __table_args__ = (
        UniqueConstraint("license_key", name="uq_license_key"),
        Index("idx_license_key", "license_key"),
        Index("idx_license_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String(255), nullable=False, unique=True)

    # Plan
    plan = Column(String(50), nullable=False)
    features = Column(JSON, default=list)
    max_accounts = Column(Integer, default=1)
    max_strategies = Column(Integer, default=3)

    # Status
    status = Column(Enum(LicenseStatus), default=LicenseStatus.PENDING)

    # Dates
    activated_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)

    # Machine binding
    machine_id = Column(String(255), nullable=True)
    ip_address = Column(String(50), nullable=True)

    # User reference (if registered)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Affiliate
    affiliate_code = Column(String(50), nullable=True)
    affiliate_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Meta
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class LicenseUsage(Base):
    __tablename__ = "license_usage"
    __table_args__ = (
        Index("idx_usage_license", "license_id"),
        Index("idx_usage_date", "usage_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    license_id = Column(Integer, ForeignKey("licenses.id", ondelete="CASCADE"), nullable=False)

    usage_date = Column(DateTime, nullable=False)
    trades_executed = Column(Integer, default=0)
    strategies_used = Column(Integer, default=0)
    api_calls = Column(BigInteger, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
