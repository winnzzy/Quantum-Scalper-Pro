"""User model with authentication and subscription."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, 
    String, Text, Float, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"
    AFFILIATE = "affiliate"


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        Index("idx_user_email", "email"),
        Index("idx_user_license", "license_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    username = Column(String(100), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)

    # Profile
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    timezone = Column(String(50), default="UTC")

    # Security
    role = Column(Enum(UserRole), default=UserRole.TRADER, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String(255), nullable=True)

    # Subscription
    subscription_plan = Column(Enum(SubscriptionPlan), default=SubscriptionPlan.FREE)
    subscription_expires_at = Column(DateTime, nullable=True)
    license_key = Column(String(255), nullable=True, unique=True)

    # Trading
    default_broker = Column(String(50), default="binance_testnet")
    paper_trading = Column(Boolean, default=True)

    # Meta
    last_login = Column(DateTime, nullable=True)
    login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    risk_profile = relationship("RiskProfile", back_populates="user", uselist=False)
    trades = relationship("Trade", back_populates="user")
    positions = relationship("Position", back_populates="user")
    strategy_configs = relationship("StrategyConfig", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    notifications = relationship("Notification", back_populates="user")

    @property
    def full_name(self) -> str:
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.username

    @property
    def is_subscribed(self) -> bool:
        if self.subscription_plan == SubscriptionPlan.FREE:
            return True
        if self.subscription_expires_at is None:
            return False
        return self.subscription_expires_at > datetime.now(timezone.utc)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        return self.locked_until > datetime.now(timezone.utc)
