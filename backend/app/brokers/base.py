"""Base broker interface and common types."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List, Any
from enum import Enum


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class BrokerConfig:
    """Broker configuration."""
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    passphrase: Optional[str] = None
    server: Optional[str] = None
    login: Optional[int] = None
    password: Optional[str] = None
    testnet: bool = True
    sandbox: bool = False
    timeout: int = 30000
    rate_limit: bool = True


@dataclass
class OrderResult:
    """Order execution result."""
    success: bool
    order_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[OrderSide] = None
    order_type: Optional[OrderType] = None
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    filled_price: Optional[Decimal] = None
    filled_quantity: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    commission: Optional[Decimal] = None
    timestamp: Optional[datetime] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


@dataclass
class AccountInfo:
    """Account information."""
    balance: Decimal = Decimal("0")
    equity: Decimal = Decimal("0")
    margin_used: Decimal = Decimal("0")
    margin_free: Decimal = Decimal("0")
    margin_level: Optional[Decimal] = None
    currency: str = "USD"
    open_positions: int = 0
    open_orders: int = 0
    unrealized_pnl: Decimal = Decimal("0")
    timestamp: Optional[datetime] = None


@dataclass
class PositionInfo:
    """Position information."""
    symbol: str
    side: OrderSide
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    leverage: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    timestamp: Optional[datetime] = None


@dataclass
class MarketData:
    """Market data snapshot."""
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume_24h: Optional[Decimal] = None
    high_24h: Optional[Decimal] = None
    low_24h: Optional[Decimal] = None
    change_24h: Optional[Decimal] = None
    change_percent_24h: Optional[Decimal] = None
    timestamp: Optional[datetime] = None


class BaseBroker(ABC):
    """Abstract base class for all broker integrations."""

    def __init__(self, config: BrokerConfig):
        self.config = config
        self.is_connected = False
        self.last_error: Optional[str] = None

    async def reconnect(self) -> bool:
        """Reconnect to the broker after a disconnect."""
        try:
            await self.disconnect()
        except Exception:
            pass
        self.is_connected = False
        return await self.connect()

    async def ensure_connection(self) -> bool:
        """Ensure the broker is connected before performing broker operations."""
        if self.is_connected:
            return True
        return await self.connect()

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to broker."""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from broker."""
        pass

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Get account information."""
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        **kwargs
    ) -> OrderResult:
        """Place an order."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """Cancel an order."""
        pass

    @abstractmethod
    async def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[OrderResult]:
        """Get order details."""
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """Get open orders."""
        pass

    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """Get open positions."""
        pass

    @abstractmethod
    async def close_position(self, symbol: str, side: Optional[OrderSide] = None) -> OrderResult:
        """Close a position."""
        pass

    @abstractmethod
    async def get_market_data(self, symbol: str) -> MarketData:
        """Get current market data."""
        pass

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[List[Any]]:
        """Get OHLCV data."""
        pass

    @abstractmethod
    async def get_balance(self, currency: Optional[str] = None) -> Decimal:
        """Get balance for currency."""
        pass

    async def health_check(self) -> bool:
        """Check broker health."""
        try:
            await self.get_account_info()
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def format_symbol(self, symbol: str) -> str:
        """Format symbol for broker."""
        return symbol.upper()
