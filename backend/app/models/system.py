"""System monitoring and audit models."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, String,
    Text, Float, JSON, Index, BigInteger
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class AuditAction(str, enum.Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    TRADE_OPEN = "trade_open"
    TRADE_CLOSE = "trade_close"
    SETTINGS_CHANGE = "settings_change"
    STRATEGY_CHANGE = "strategy_change"
    RISK_OVERRIDE = "risk_override"
    PAUSE_TRADING = "pause_trading"
    RESUME_TRADING = "resume_trading"
    WITHDRAWAL = "withdrawal"
    API_KEY_CHANGE = "api_key_change"
    PASSWORD_CHANGE = "password_change"
    LICENSE_ACTIVATE = "license_activate"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_time", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    action = Column(Enum(AuditAction), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(Integer, nullable=True)

    details = Column(JSON, default=dict)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)

    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="audit_logs")


class SystemHealth(Base):
    __tablename__ = "system_health"
    __table_args__ = (
        Index("idx_health_time", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Component status
    component = Column(String(50), nullable=False)
    status = Column(String(20), default="healthy")  # healthy, degraded, down

    # Metrics
    cpu_percent = Column(Float, nullable=True)
    memory_percent = Column(Float, nullable=True)
    disk_percent = Column(Float, nullable=True)

    # Trading metrics
    active_trades = Column(Integer, default=0)
    queue_size = Column(Integer, default=0)
    latency_ms = Column(Float, nullable=True)

    # Broker status
    broker_status = Column(JSON, default=dict)

    # Error count
    error_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)

    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notif_user", "user_id"),
        Index("idx_notif_read", "is_read"),
        Index("idx_notif_time", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    type = Column(String(50), nullable=False)  # trade, risk, system, news
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Priority
    priority = Column(String(20), default="normal")  # low, normal, high, critical

    # Delivery
    channels = Column(JSON, default=list)  # web, telegram, email
    delivered = Column(JSON, default=dict)

    # Read status
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)

    # Action
    action_url = Column(String(500), nullable=True)
    action_text = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="notifications")
