"""Paper trading broker - simulates trading without real money."""
import asyncio
import random
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Optional, List, Any, Dict
from collections import defaultdict

from app.brokers.base import (
    BaseBroker, BrokerConfig, OrderResult, AccountInfo,
    PositionInfo, MarketData, OrderSide, OrderType, OrderStatus
)
from app.core.logging import logger


class PaperBroker(BaseBroker):
    """Paper trading broker for testing strategies."""

    def __init__(self, config: BrokerConfig):
        super().__init__(config)
        self._balance: Decimal = Decimal("100000.00")  # Default paper balance
        self._positions: Dict[str, PositionInfo] = {}
        self._orders: Dict[str, OrderResult] = {}
        self._order_counter = 0
        self._trade_history: List[OrderResult] = []
        self._market_data: Dict[str, MarketData] = {}
        self._commission_rate = Decimal("0.0004")  # 0.04%
        self._slippage = Decimal("0.0001")  # 0.01%

    async def connect(self) -> bool:
        """Connect to paper trading."""
        self.is_connected = True
        logger.info("Paper trading connected with $100,000 balance")
        return True

    async def disconnect(self) -> bool:
        """Disconnect."""
        self.is_connected = False
        logger.info("Paper trading disconnected")
        return True

    async def get_account_info(self) -> AccountInfo:
        """Get account info."""
        unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        equity = self._balance + unrealized

        return AccountInfo(
            balance=self._balance,
            equity=equity,
            margin_used=Decimal("0"),
            margin_free=equity,
            currency="USD",
            open_positions=len(self._positions),
            open_orders=len([o for o in self._orders.values() if o.status == OrderStatus.OPEN]),
            unrealized_pnl=unrealized,
            timestamp=datetime.now(timezone.utc)
        )

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
        """Simulate order placement."""
        self._order_counter += 1
        order_id = f"PAPER_{self._order_counter}"

        # Get current market price
        market = await self.get_market_data(symbol)

        if order_type == OrderType.MARKET:
            fill_price = market.ask if side == OrderSide.BUY else market.bid
            # Apply slippage
            slippage = fill_price * self._slippage
            fill_price = fill_price + slippage if side == OrderSide.BUY else fill_price - slippage
        else:
            fill_price = price or market.last

        # Calculate commission
        notional = fill_price * quantity
        commission = notional * self._commission_rate

        # Update balance
        if side == OrderSide.BUY:
            cost = notional + commission
            if cost > self._balance:
                return OrderResult(
                    success=False,
                    error_message=f"Insufficient balance. Required: {cost}, Available: {self._balance}"
                )
            self._balance -= cost

        # Create position
        position = PositionInfo(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=fill_price,
            current_price=fill_price,
            unrealized_pnl=Decimal("0"),
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=datetime.now(timezone.utc)
        )

        self._positions[symbol] = position

        result = OrderResult(
            success=True,
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            filled_price=fill_price,
            filled_quantity=quantity,
            status=OrderStatus.FILLED,
            commission=commission,
            timestamp=datetime.now(timezone.utc)
        )

        self._orders[order_id] = result
        self._trade_history.append(result)

        logger.info(f"Paper trade executed: {side.value} {quantity} {symbol} @ {fill_price}")
        return result

    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """Cancel order."""
        if order_id in self._orders:
            self._orders[order_id].status = OrderStatus.CANCELLED
            return True
        return False

    async def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[OrderResult]:
        """Get order."""
        return self._orders.get(order_id)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """Get open orders."""
        orders = [o for o in self._orders.values() if o.status == OrderStatus.OPEN]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    async def get_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """Get positions."""
        if symbol:
            pos = self._positions.get(symbol)
            return [pos] if pos else []
        return list(self._positions.values())

    async def close_position(self, symbol: str, side: Optional[OrderSide] = None) -> OrderResult:
        """Close position."""
        position = self._positions.get(symbol)
        if not position:
            return OrderResult(success=False, error_message="No position found")

        market = await self.get_market_data(symbol)
        exit_price = market.bid if position.side == OrderSide.BUY else market.ask

        # Calculate P&L
        if position.side == OrderSide.BUY:
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity

        # Commission on exit
        notional = exit_price * position.quantity
        commission = notional * self._commission_rate
        net_pnl = pnl - commission

        # Update balance
        self._balance += notional + net_pnl if position.side == OrderSide.BUY else notional - net_pnl

        self._order_counter += 1
        result = OrderResult(
            success=True,
            order_id=f"PAPER_CLOSE_{self._order_counter}",
            symbol=symbol,
            side=OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            filled_price=exit_price,
            filled_quantity=position.quantity,
            status=OrderStatus.FILLED,
            commission=commission,
            timestamp=datetime.now(timezone.utc)
        )

        del self._positions[symbol]
        self._trade_history.append(result)

        logger.info(f"Paper position closed: {symbol} P&L: {net_pnl}")
        return result

    async def get_market_data(self, symbol: str) -> MarketData:
        """Simulate market data."""
        if symbol in self._market_data:
            # Add small random movement
            base = self._market_data[symbol]
            noise = Decimal(str(random.uniform(-0.001, 0.001)))
            new_last = base.last * (Decimal("1") + noise)
            spread = base.ask - base.bid

            return MarketData(
                symbol=symbol,
                bid=new_last - spread / 2,
                ask=new_last + spread / 2,
                last=new_last,
                volume_24h=base.volume_24h,
                high_24h=max(base.high_24h, new_last) if base.high_24h else new_last,
                low_24h=min(base.low_24h, new_last) if base.low_24h else new_last,
                timestamp=datetime.now(timezone.utc)
            )

        # Generate realistic default prices
        base_prices = {
            "BTC/USDT": 65000, "ETH/USDT": 3500, "BNB/USDT": 600,
            "SOL/USDT": 150, "XRP/USDT": 0.60, "ADA/USDT": 0.45,
            "EUR/USD": 1.0850, "GBP/USD": 1.2650, "USD/JPY": 151.50,
            "AUD/USD": 0.6650, "USD/CHF": 0.9050, "EUR/JPY": 164.50,
        }

        base_price = base_prices.get(symbol, 100.0)
        price = Decimal(str(base_price * (1 + random.uniform(-0.002, 0.002))))
        spread = price * Decimal("0.0002")  # 0.02% spread

        return MarketData(
            symbol=symbol,
            bid=price - spread / 2,
            ask=price + spread / 2,
            last=price,
            volume_24h=Decimal(str(random.uniform(1e6, 1e9))),
            high_24h=price * Decimal("1.02"),
            low_24h=price * Decimal("0.98"),
            change_24h=price * Decimal(str(random.uniform(-0.05, 0.05))),
            change_percent_24h=Decimal(str(random.uniform(-5, 5))),
            timestamp=datetime.now(timezone.utc)
        )

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[List[Any]]:
        """Generate simulated OHLCV data."""
        market = await self.get_market_data(symbol)
        base_price = float(market.last)

        ohlcv = []
        now = datetime.now(timezone.utc)

        for i in range(limit, 0, -1):
            timestamp = int((now.timestamp() - i * 60) * 1000)
            open_p = base_price * (1 + random.uniform(-0.01, 0.01))
            high_p = open_p * (1 + random.uniform(0, 0.005))
            low_p = open_p * (1 - random.uniform(0, 0.005))
            close_p = low_p + random.uniform(0, high_p - low_p)
            volume = random.uniform(100, 10000)

            ohlcv.append([timestamp, round(open_p, 2), round(high_p, 2), round(low_p, 2), round(close_p, 2), round(volume, 2)])

        return ohlcv

    async def get_balance(self, currency: Optional[str] = None) -> Decimal:
        """Get balance."""
        return self._balance

    def set_balance(self, amount: Decimal):
        """Set paper balance."""
        self._balance = amount

    def set_market_data(self, symbol: str, data: MarketData):
        """Set market data for testing."""
        self._market_data[symbol] = data

    def update_positions(self, symbol: str, current_price: Decimal):
        """Update position unrealized P&L."""
        if symbol in self._positions:
            pos = self._positions[symbol]
            pos.current_price = current_price
            if pos.side == OrderSide.BUY:
                pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - current_price) * pos.quantity
