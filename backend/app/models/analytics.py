"""Analytics and reporting models."""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text, 
    Float, Numeric, JSON, Index, BigInteger
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class TradeJournal(Base):
    __tablename__ = "trade_journals"
    __table_args__ = (
        Index("idx_journal_user", "user_id"),
        Index("idx_journal_trade", "trade_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    trade_id = Column(Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)

    # Journal entry
    pre_trade_notes = Column(Text, nullable=True)
    post_trade_notes = Column(Text, nullable=True)
    emotions = Column(String(50), nullable=True)
    lessons_learned = Column(Text, nullable=True)

    # Tags
    tags = Column(JSON, default=list)

    # Screenshots (URLs)
    entry_screenshot = Column(String(500), nullable=True)
    exit_screenshot = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PerformanceReport(Base):
    __tablename__ = "performance_reports"
    __table_args__ = (
        Index("idx_report_user", "user_id"),
        Index("idx_report_period", "period_start", "period_end"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(String(20), nullable=False)  # daily, weekly, monthly, yearly

    # Trade statistics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Numeric(5, 2), default=0)

    # P&L
    gross_profit = Column(Numeric(20, 8), default=0)
    gross_loss = Column(Numeric(20, 8), default=0)
    net_profit = Column(Numeric(20, 8), default=0)

    # Ratios
    profit_factor = Column(Numeric(10, 4), default=0)
    sharpe_ratio = Column(Numeric(10, 4), default=0)
    sortino_ratio = Column(Numeric(10, 4), default=0)
    recovery_factor = Column(Numeric(10, 4), default=0)
    expectancy = Column(Numeric(20, 8), default=0)

    # Drawdown
    max_drawdown = Column(Numeric(10, 4), default=0)
    max_drawdown_percent = Column(Numeric(5, 2), default=0)
    avg_drawdown = Column(Numeric(10, 4), default=0)

    # Trade metrics
    avg_win = Column(Numeric(20, 8), default=0)
    avg_loss = Column(Numeric(20, 8), default=0)
    largest_win = Column(Numeric(20, 8), default=0)
    largest_loss = Column(Numeric(20, 8), default=0)
    avg_trade_duration = Column(Numeric(10, 2), default=0)  # minutes

    # Strategy breakdown
    strategy_performance = Column(JSON, default=dict)
    symbol_performance = Column(JSON, default=dict)

    # Time analysis
    hourly_distribution = Column(JSON, default=dict)
    daily_distribution = Column(JSON, default=dict)

    # Equity curve data (serialized)
    equity_curve = Column(JSON, default=list)
    drawdown_curve = Column(JSON, default=list)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
