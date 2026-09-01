"""Trading models for trades, positions, and orders."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, 
    String, Text, Float, JSON, Numeric, Index, BigInteger, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class TradeStatus(str, enum.Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ERROR = "error"


class TradeDirection(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class BrokerType(str, enum.Enum):
    BINANCE_SPOT = "binance_spot"
    BINANCE_FUTURES = "binance_futures"
    BINANCE_TESTNET = "binance_testnet"
    MT5 = "mt5"
    PAPER = "paper"


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("idx_trade_user", "user_id"),
        Index("idx_trade_status", "status"),
        Index("idx_trade_symbol", "symbol"),
        Index("idx_trade_opened", "entry_time"),
        Index("idx_trade_strategy", "strategy_name"),
        UniqueConstraint("broker", "broker_order_id", name="uq_trade_broker_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Trade details
    symbol = Column(String(20), nullable=False)
    direction = Column(Enum(TradeDirection), nullable=False)
    status = Column(Enum(TradeStatus), default=TradeStatus.PENDING)

    # Entry
    entry_price = Column(Numeric(20, 8), nullable=True)
    entry_time = Column(DateTime, nullable=True)
    quantity = Column(Numeric(20, 8), nullable=True)

    # Exit
    exit_price = Column(Numeric(20, 8), nullable=True)
    exit_time = Column(DateTime, nullable=True)

    # P&L
    gross_pnl = Column(Numeric(20, 8), default=0)
    net_pnl = Column(Numeric(20, 8), default=0)
    commission = Column(Numeric(20, 8), default=0)
    swap = Column(Numeric(20, 8), default=0)

    # Risk
    stop_loss = Column(Numeric(20, 8), nullable=True)
    take_profit = Column(Numeric(20, 8), nullable=True)
    risk_percent = Column(Numeric(5, 2), nullable=True)
    risk_amount = Column(Numeric(20, 8), nullable=True)

    # Strategy
    strategy_name = Column(String(50), nullable=True)
    strategy_config = Column(JSON, default=dict)

    # AI Filter
    ai_confidence = Column(Numeric(5, 4), nullable=True)
    ai_quality_score = Column(Numeric(5, 4), nullable=True)

    # Broker
    broker = Column(Enum(BrokerType), nullable=False)
    broker_trade_id = Column(String(100), nullable=True)
    broker_order_id = Column(String(100), nullable=True)

    # Meta
    notes = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="trades")
    orders = relationship("Order", back_populates="trade")

    @property
    def is_open(self) -> bool:
        return self.status == TradeStatus.OPEN

    @property
    def is_profitable(self) -> bool:
        if self.net_pnl is None:
            return False
        return float(self.net_pnl) > 0

    @property
    def duration_minutes(self) -> float:
        if not self.entry_time:
            return 0
        end = self.exit_time or datetime.now(timezone.utc)
        return (end - self.entry_time).total_seconds() / 60


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index("idx_position_user", "user_id"),
        Index("idx_position_symbol", "symbol"),
        Index("idx_position_open", "is_open"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    symbol = Column(String(20), nullable=False)
    direction = Column(Enum(TradeDirection), nullable=False)
    is_open = Column(Boolean, default=True)

    # Quantity
    quantity = Column(Numeric(20, 8), nullable=False)
    filled_quantity = Column(Numeric(20, 8), default=0)

    # Prices
    average_entry_price = Column(Numeric(20, 8), nullable=False)
    current_price = Column(Numeric(20, 8), nullable=True)
    unrealized_pnl = Column(Numeric(20, 8), default=0)

    # Risk
    stop_loss = Column(Numeric(20, 8), nullable=True)
    take_profit = Column(Numeric(20, 8), nullable=True)

    # Broker
    broker = Column(Enum(BrokerType), nullable=False)
    broker_position_id = Column(String(100), nullable=True)

    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="positions")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("idx_order_trade", "trade_id"),
        Index("idx_order_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    order_type = Column(Enum(OrderType), nullable=False)
    direction = Column(Enum(TradeDirection), nullable=False)
    status = Column(String(20), default="pending")

    symbol = Column(String(20), nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=True)
    filled_price = Column(Numeric(20, 8), nullable=True)
    filled_quantity = Column(Numeric(20, 8), default=0)

    broker_order_id = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    executed_at = Column(DateTime, nullable=True)

    trade = relationship("Trade", back_populates="orders")


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"
    __table_args__ = (
        Index("idx_strategy_user", "user_id"),
        Index("idx_strategy_name", "name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(50), nullable=False)
    strategy_type = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    # Configuration
    parameters = Column(JSON, default=dict)
    symbols = Column(JSON, default=list)
    timeframes = Column(JSON, default=list)

    # Risk overrides
    risk_per_trade = Column(Numeric(5, 2), nullable=True)
    max_trades_per_day = Column(Integer, nullable=True)

    # Filters
    use_ai_filter = Column(Boolean, default=True)
    use_news_filter = Column(Boolean, default=True)
    min_confidence = Column(Numeric(5, 4), default=0.65)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="strategy_configs")
