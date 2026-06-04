"""Risk management models."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, 
    String, Text, Float, Numeric, JSON, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class RiskEventType(str, enum.Enum):
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    WEEKLY_LOSS_LIMIT = "weekly_loss_limit"
    MONTHLY_LOSS_LIMIT = "monthly_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    SPREAD_PROTECTION = "spread_protection"
    VOLATILITY_PROTECTION = "volatility_protection"
    WEEKEND_PROTECTION = "weekend_protection"
    NEWS_LOCK = "news_lock"
    BROKER_DISCONNECT = "broker_disconnect"
    MANUAL_PAUSE = "manual_pause"


class RiskProfile(Base):
    __tablename__ = "risk_profiles"
    __table_args__ = (
        Index("idx_risk_user", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Risk per trade
    risk_per_trade_percent = Column(Numeric(5, 2), default=0.5)
    risk_per_trade_custom = Column(Numeric(5, 2), nullable=True)

    # Loss limits
    daily_loss_limit_percent = Column(Numeric(5, 2), default=3.0)
    weekly_loss_limit_percent = Column(Numeric(5, 2), default=5.0)
    monthly_loss_limit_percent = Column(Numeric(5, 2), default=10.0)

    # Drawdown
    max_drawdown_percent = Column(Numeric(5, 2), default=15.0)

    # Consecutive losses
    max_consecutive_losses = Column(Integer, default=5)

    # Trade limits
    max_open_trades = Column(Integer, default=10)
    max_trades_per_day = Column(Integer, default=20)
    max_trades_per_week = Column(Integer, default=50)

    # Protections
    spread_protection_enabled = Column(Boolean, default=True)
    max_spread_pips = Column(Numeric(10, 5), default=5.0)

    volatility_protection_enabled = Column(Boolean, default=True)
    max_volatility_percent = Column(Numeric(5, 2), default=5.0)

    weekend_protection_enabled = Column(Boolean, default=True)

    news_protection_enabled = Column(Boolean, default=True)
    news_buffer_minutes = Column(Integer, default=30)

    # Mandatory rules
    mandatory_stop_loss = Column(Boolean, default=True)
    mandatory_take_profit = Column(Boolean, default=False)

    # Position sizing
    position_sizing_method = Column(String(20), default="fixed_percent")  # fixed_percent, fixed_amount, kelly, optimal_f
    fixed_position_size = Column(Numeric(20, 8), nullable=True)

    # Current state
    current_daily_loss = Column(Numeric(20, 8), default=0)
    current_weekly_loss = Column(Numeric(20, 8), default=0)
    current_monthly_loss = Column(Numeric(20, 8), default=0)
    current_drawdown = Column(Numeric(5, 2), default=0)
    consecutive_losses = Column(Integer, default=0)

    # Trading state
    trading_paused = Column(Boolean, default=False)
    pause_reason = Column(String(100), nullable=True)
    paused_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="risk_profile")


class RiskEvent(Base):
    __tablename__ = "risk_events"
    __table_args__ = (
        Index("idx_risk_event_user", "user_id"),
        Index("idx_risk_event_type", "event_type"),
        Index("idx_risk_event_time", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    event_type = Column(Enum(RiskEventType), nullable=False)
    severity = Column(String(20), default="warning")  # info, warning, critical

    message = Column(Text, nullable=False)
    details = Column(JSON, default=dict)

    # Trade reference
    trade_id = Column(Integer, ForeignKey("trades.id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String(20), nullable=True)

    # Resolution
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
