"""MetaTrader 5 broker integration."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Any

try:
    import MetaTrader5 as mt5
except ImportError:  # MetaTrader5 only publishes Windows wheels.
    mt5 = None

from app.brokers.base import (
    BaseBroker, BrokerConfig, OrderResult, AccountInfo,
    PositionInfo, MarketData, OrderSide, OrderType, OrderStatus
)
from app.core.logging import logger


class MT5Broker(BaseBroker):
    """MetaTrader 5 broker integration."""

    def __init__(self, config: BrokerConfig):
        super().__init__(config)
        self._initialized = False

    async def connect(self) -> bool:
        """Initialize MT5 connection."""
        if mt5 is None:
            self.last_error = (
                "MetaTrader5 is unavailable on this platform. "
                "Run the MT5 adapter on Windows or use paper/Binance trading."
            )
            logger.error(self.last_error)
            return False

        try:
            loop = asyncio.get_event_loop()

            def _init():
                if not mt5.initialize(
                    path=self.config.server,
                    login=self.config.login,
                    password=self.config.password,
                    server=self.config.server,
                    timeout=self.config.timeout
                ):
                    return False, mt5.last_error()
                return True, None

            success, error = await loop.run_in_executor(None, _init)

            if not success:
                self.last_error = f"MT5 init failed: {error}"
                logger.error(self.last_error)
                return False

            self._initialized = True
            self.is_connected = True
            logger.info("MT5 connected successfully")
            return True

        except Exception as e:
            self.last_error = f"MT5 connection failed: {str(e)}"
            logger.error(self.last_error)
            return False

    async def disconnect(self) -> bool:
        """Shutdown MT5."""
        if self._initialized:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, mt5.shutdown)
            self._initialized = False
            self.is_connected = False
            logger.info("MT5 disconnected")
        return True

    async def get_account_info(self) -> AccountInfo:
        """Get MT5 account info."""
        if not self._initialized:
            raise RuntimeError("MT5 not initialized")

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, mt5.account_info)

        if info is None:
            raise RuntimeError("Failed to get account info")

        return AccountInfo(
            balance=Decimal(str(info.balance)),
            equity=Decimal(str(info.equity)),
            margin_used=Decimal(str(info.margin)),
            margin_free=Decimal(str(info.margin_free)),
            margin_level=Decimal(str(info.margin_level)) if info.margin_level else None,
            currency=info.currency,
            open_positions=info.positions,
            open_orders=info.orders,
            unrealized_pnl=Decimal(str(info.profit)),
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
        """Place order via MT5."""
        if not self._initialized:
            return OrderResult(success=False, error_message="MT5 not initialized")

        try:
            loop = asyncio.get_event_loop()

            mt5_type = {
                OrderType.MARKET: mt5.ORDER_TYPE_BUY if side == OrderSide.BUY else mt5.ORDER_TYPE_SELL,
                OrderType.LIMIT: mt5.ORDER_TYPE_BUY_LIMIT if side == OrderSide.BUY else mt5.ORDER_TYPE_SELL_LIMIT,
                OrderType.STOP: mt5.ORDER_TYPE_BUY_STOP if side == OrderSide.BUY else mt5.ORDER_TYPE_SELL_STOP,
            }.get(order_type, mt5.ORDER_TYPE_BUY if side == OrderSide.BUY else mt5.ORDER_TYPE_SELL)

            request = {
                "action": mt5.TRADE_ACTION_DEAL if order_type == OrderType.MARKET else mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": float(quantity),
                "type": mt5_type,
                "deviation": kwargs.get("deviation", 10),
                "magic": kwargs.get("magic", 123456),
                "comment": kwargs.get("comment", "QSP"),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            if price:
                request["price"] = float(price)
            if stop_loss:
                request["sl"] = float(stop_loss)
            if take_profit:
                request["tp"] = float(take_profit)

            def _send():
                result = mt5.order_send(request)
                return result

            result = await loop.run_in_executor(None, _send)

            if result is None:
                return OrderResult(success=False, error_message=f"Order send failed: {mt5.last_error()}")

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return OrderResult(success=False, error_message=f"Order failed: {result.retcode}")

            return OrderResult(
                success=True,
                order_id=str(result.order),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                filled_price=Decimal(str(result.price)),
                status=OrderStatus.FILLED if order_type == OrderType.MARKET else OrderStatus.OPEN,
                timestamp=datetime.now(timezone.utc)
            )

        except Exception as e:
            logger.error(f"MT5 order failed: {e}")
            return OrderResult(success=False, error_message=str(e))

    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """Cancel pending order."""
        if not self._initialized:
            return False
        try:
            loop = asyncio.get_event_loop()
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": int(order_id),
            }
            def _cancel():
                return mt5.order_send(request)
            result = await loop.run_in_executor(None, _cancel)
            return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    async def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[OrderResult]:
        """Get order from MT5."""
        if not self._initialized:
            return None
        try:
            loop = asyncio.get_event_loop()
            def _get():
                return mt5.orders_get(ticket=int(order_id))
            orders = await loop.run_in_executor(None, _get)
            if orders and len(orders) > 0:
                order = orders[0]
                return OrderResult(
                    success=True,
                    order_id=str(order.ticket),
                    symbol=order.symbol,
                    side=OrderSide.BUY if order.type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP] else OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    quantity=Decimal(str(order.volume_current)),
                    price=Decimal(str(order.price_open)),
                    status=OrderStatus.OPEN,
                    timestamp=datetime.now(timezone.utc)
                )
            return None
        except Exception as e:
            logger.error(f"Get order failed: {e}")
            return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """Get open orders."""
        if not self._initialized:
            return []
        try:
            loop = asyncio.get_event_loop()
            def _get():
                if symbol:
                    return mt5.orders_get(symbol=symbol)
                return mt5.orders_get()
            orders = await loop.run_in_executor(None, _get)
            return [self._parse_mt5_order(o) for o in (orders or [])]
        except Exception as e:
            logger.error(f"Get open orders failed: {e}")
            return []

    async def get_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """Get positions."""
        if not self._initialized:
            return []
        try:
            loop = asyncio.get_event_loop()
            def _get():
                if symbol:
                    return mt5.positions_get(symbol=symbol)
                return mt5.positions_get()
            positions = await loop.run_in_executor(None, _get)
            return [self._parse_mt5_position(p) for p in (positions or [])]
        except Exception as e:
            logger.error(f"Get positions failed: {e}")
            return []

    async def close_position(self, symbol: str, side: Optional[OrderSide] = None) -> OrderResult:
        """Close position."""
        positions = await self.get_positions(symbol)
        if not positions:
            return OrderResult(success=False, error_message="No position found")

        pos = positions[0]
        close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY

        return await self.place_order(
            symbol=symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=pos.quantity
        )

    async def get_market_data(self, symbol: str) -> MarketData:
        """Get market data."""
        if not self._initialized:
            raise RuntimeError("MT5 not initialized")

        loop = asyncio.get_event_loop()
        tick = await loop.run_in_executor(None, mt5.symbol_info_tick, symbol)

        if tick is None:
            raise RuntimeError(f"Failed to get tick for {symbol}")

        return MarketData(
            symbol=symbol,
            bid=Decimal(str(tick.bid)),
            ask=Decimal(str(tick.ask)),
            last=Decimal(str(tick.last)),
            volume_24h=None,
            timestamp=datetime.now(timezone.utc)
        )

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[List[Any]]:
        """Get OHLCV from MT5."""
        if not self._initialized:
            return []

        tf_map = {
            "1m": mt5.TIMEFRAME_M1,
            "5m": mt5.TIMEFRAME_M5,
            "15m": mt5.TIMEFRAME_M15,
            "30m": mt5.TIMEFRAME_M30,
            "1h": mt5.TIMEFRAME_H1,
            "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1,
        }

        mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)

        try:
            loop = asyncio.get_event_loop()
            def _get():
                return mt5.copy_rates_from_pos(symbol, mt5_tf, 0, limit)
            rates = await loop.run_in_executor(None, _get)

            if rates is None:
                return []

            # Convert to list format [timestamp, open, high, low, close, volume]
            return [
                [
                    int(r.time) * 1000,  # Convert to ms timestamp
                    float(r.open),
                    float(r.high),
                    float(r.low),
                    float(r.close),
                    float(r.tick_volume)
                ]
                for r in rates
            ]
        except Exception as e:
            logger.error(f"Get OHLCV failed: {e}")
            return []

    async def get_balance(self, currency: Optional[str] = None) -> Decimal:
        """Get balance."""
        info = await self.get_account_info()
        return info.balance

    def _parse_mt5_order(self, order) -> OrderResult:
        """Parse MT5 order."""
        side = OrderSide.BUY if order.type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP] else OrderSide.SELL
        return OrderResult(
            success=True,
            order_id=str(order.ticket),
            symbol=order.symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=Decimal(str(order.volume_current)),
            price=Decimal(str(order.price_open)),
            status=OrderStatus.OPEN,
            timestamp=datetime.now(timezone.utc)
        )

    def _parse_mt5_position(self, pos) -> PositionInfo:
        """Parse MT5 position."""
        side = OrderSide.BUY if pos.type == mt5.ORDER_TYPE_BUY else OrderSide.SELL
        return PositionInfo(
            symbol=pos.symbol,
            side=side,
            quantity=Decimal(str(pos.volume)),
            entry_price=Decimal(str(pos.price_open)),
            current_price=Decimal(str(pos.price_current)),
            unrealized_pnl=Decimal(str(pos.profit)),
            stop_loss=Decimal(str(pos.sl)) if pos.sl else None,
            take_profit=Decimal(str(pos.tp)) if pos.tp else None,
            leverage=None,
            margin=Decimal(str(pos.margin)) if hasattr(pos, 'margin') else None,
            timestamp=datetime.now(timezone.utc)
        )
