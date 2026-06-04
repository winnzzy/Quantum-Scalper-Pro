"""Binance broker integration using CCXT."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Optional, List, Any, Dict

import ccxt.async_support as ccxt

from app.brokers.base import (
    BaseBroker, BrokerConfig, OrderResult, AccountInfo,
    PositionInfo, MarketData, OrderSide, OrderType, OrderStatus
)
from app.core.logging import logger


class BinanceBroker(BaseBroker):
    """Binance Spot/Futures broker integration."""

    def __init__(self, config: BrokerConfig):
        super().__init__(config)
        self.exchange: Optional[ccxt.binance] = None
        self.market_type = "future" if not config.testnet else "spot"
        self._is_futures = config.testnet is False  # Futures for live

    async def _exchange_ready(self) -> bool:
        if self.exchange is None or not self.is_connected:
            return await self.connect()
        return True

    async def _retryable(self, fn, *args, **kwargs):
        for attempt in range(2):
            if not await self._exchange_ready():
                break
            try:
                return await fn(*args, **kwargs)
            except (ccxt.RequestTimeout, ccxt.NetworkError, ccxt.ExchangeError) as e:
                self.last_error = str(e)
                self.is_connected = False
                logger.warning(f"Binance API transient error on attempt {attempt + 1}: {e}")
                if attempt == 0:
                    await self.connect()
                    continue
                raise

    async def connect(self) -> bool:
        """Connect to Binance."""
        try:
            config = {
                "apiKey": self.config.api_key or "",
                "secret": self.config.secret_key or "",
                "enableRateLimit": self.config.rate_limit,
                "timeout": self.config.timeout,
                "options": {
                    "defaultType": "future" if self._is_futures else "spot",
                    "adjustForTimeDifference": True,
                }
            }

            if self.config.testnet:
                config["options"]["testnet"] = True
                config["urls"] = {"api": {"future": "https://testnet.binancefuture.com"}}

            self.exchange = ccxt.binance(config)
            await self.exchange.load_markets()
            self.is_connected = True
            logger.info(f"Binance connected. Testnet: {self.config.testnet}")
            return True

        except Exception as e:
            self.last_error = f"Binance connection failed: {str(e)}"
            logger.error(self.last_error)
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Binance."""
        if self.exchange:
            await self.exchange.close()
            self.is_connected = False
            logger.info("Binance disconnected")
        return True

    async def get_account_info(self) -> AccountInfo:
        """Get account info."""
        async def _get_account_info():
            return await self.exchange.fetch_balance()

        try:
            balance = await self._retryable(_get_account_info)
            total = Decimal(str(balance.get("total", {}).get("USDT", 0)))
            free = Decimal(str(balance.get("free", {}).get("USDT", 0)))
            used = Decimal(str(balance.get("used", {}).get("USDT", 0)))

            return AccountInfo(
                balance=total,
                equity=total,
                margin_used=used,
                margin_free=free,
                currency="USDT",
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"Get account info failed: {e}")
            raise

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
        """Place order on Binance."""

        async def _place():
            ccxt_side = "buy" if side == OrderSide.BUY else "sell"
            ccxt_type = order_type.value

            # Format symbol
            formatted_symbol = self.format_symbol(symbol)

            # Get market precision
            market = self.exchange.market(formatted_symbol)

            # Format quantity and price
            formatted_qty = float(self.exchange.amount_to_precision(formatted_symbol, float(quantity)))
            formatted_price = float(self.exchange.price_to_precision(formatted_symbol, float(price))) if price else None

            params = {}
            if stop_loss:
                params["stopLoss"] = {"triggerPrice": float(stop_loss)}
            if take_profit:
                params["takeProfit"] = {"triggerPrice": float(take_profit)}

            # Merge any extra params
            params.update(kwargs)

            return await self.exchange.create_order(
                formatted_symbol,
                ccxt_type,
                ccxt_side,
                formatted_qty,
                formatted_price,
                params
            )

        try:
            order = await self._retryable(_place)
            if not order:
                return OrderResult(success=False, error_message="Binance order failed to execute")

            return OrderResult(
                success=True,
                order_id=str(order.get("id", "")),
                symbol=self.format_symbol(symbol),
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                filled_price=Decimal(str(order.get("average", 0))) if order.get("average") else None,
                filled_quantity=Decimal(str(order.get("filled", 0))) if order.get("filled") else None,
                status=self._map_status(order.get("status", "")),
                commission=Decimal(str(order.get("fee", {}).get("cost", 0))) if order.get("fee") else None,
                timestamp=datetime.now(timezone.utc),
                raw_response=order
            )

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return OrderResult(success=False, error_message=str(e))

    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """Cancel order."""
        async def _cancel():
            await self.exchange.cancel_order(order_id, self.format_symbol(symbol) if symbol else None)
            return True

        try:
            return await self._retryable(_cancel)
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    async def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[OrderResult]:
        """Get order details."""
        async def _get_order():
            return await self.exchange.fetch_order(order_id, self.format_symbol(symbol) if symbol else None)

        try:
            order = await self._retryable(_get_order)
            if order is None:
                return None
            return self._parse_order(order)
        except Exception as e:
            logger.error(f"Get order failed: {e}")
            return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """Get open orders."""
        async def _get_open_orders():
            return await self.exchange.fetch_open_orders(self.format_symbol(symbol) if symbol else None)

        try:
            orders = await self._retryable(_get_open_orders)
            return [self._parse_order(o) for o in orders] if orders else []
        except Exception as e:
            logger.error(f"Get open orders failed: {e}")
            return []

    async def get_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """Get positions."""
        async def _get_positions():
            if self._is_futures:
                return await self.exchange.fetch_positions([self.format_symbol(symbol)] if symbol else None)
            return []

        try:
            positions = await self._retryable(_get_positions)
            if not positions:
                return []
            return [self._parse_position(p) for p in positions if float(p.get("contracts", 0)) != 0]
        except Exception as e:
            logger.error(f"Get positions failed: {e}")
            return []

    async def close_position(self, symbol: str, side: Optional[OrderSide] = None) -> OrderResult:
        """Close position."""
        if not self.exchange:
            return OrderResult(success=False, error_message="Not connected")

        try:
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
        except Exception as e:
            return OrderResult(success=False, error_message=str(e))

    async def get_market_data(self, symbol: str) -> MarketData:
        """Get market data."""
        async def _get_ticker():
            return await self.exchange.fetch_ticker(self.format_symbol(symbol))

        try:
            ticker = await self._retryable(_get_ticker)
            if not ticker:
                raise RuntimeError("Failed to fetch ticker")

            return MarketData(
                symbol=symbol,
                bid=Decimal(str(ticker.get("bid", 0))),
                ask=Decimal(str(ticker.get("ask", 0))),
                last=Decimal(str(ticker.get("last", 0))),
                volume_24h=Decimal(str(ticker.get("quoteVolume", 0))),
                high_24h=Decimal(str(ticker.get("high", 0))),
                low_24h=Decimal(str(ticker.get("low", 0))),
                change_24h=Decimal(str(ticker.get("change", 0))),
                change_percent_24h=Decimal(str(ticker.get("percentage", 0))),
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"Get market data failed: {e}")
            raise

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[List[Any]]:
        """Get OHLCV data."""
        async def _get_ohlcv():
            return await self.exchange.fetch_ohlcv(
                self.format_symbol(symbol),
                timeframe,
                since=since,
                limit=limit
            )

        try:
            return await self._retryable(_get_ohlcv)
        except Exception as e:
            logger.error(f"Get OHLCV failed: {e}")
            return []

    async def get_balance(self, currency: Optional[str] = None) -> Decimal:
        """Get balance."""
        async def _get_balance():
            return await self.exchange.fetch_balance()

        try:
            balance = await self._retryable(_get_balance)
            curr = currency or "USDT"
            return Decimal(str(balance.get("total", {}).get(curr, 0)))
        except Exception as e:
            logger.error(f"Get balance failed: {e}")
            return Decimal("0")

    def _map_status(self, status: str) -> OrderStatus:
        """Map CCXT status to internal status."""
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.EXPIRED,
            "pending": OrderStatus.PENDING,
        }
        return status_map.get(status.lower(), OrderStatus.PENDING)

    def _parse_order(self, order: Dict) -> OrderResult:
        """Parse CCXT order to OrderResult."""
        side = OrderSide.BUY if order.get("side") == "buy" else OrderSide.SELL
        order_type = OrderType(order.get("type", "market"))

        return OrderResult(
            success=True,
            order_id=str(order.get("id", "")),
            symbol=order.get("symbol", ""),
            side=side,
            order_type=order_type,
            quantity=Decimal(str(order.get("amount", 0))) if order.get("amount") else None,
            price=Decimal(str(order.get("price", 0))) if order.get("price") else None,
            filled_price=Decimal(str(order.get("average", 0))) if order.get("average") else None,
            filled_quantity=Decimal(str(order.get("filled", 0))) if order.get("filled") else None,
            status=self._map_status(order.get("status", "")),
            commission=Decimal(str(order.get("fee", {}).get("cost", 0))) if order.get("fee") else None,
            timestamp=datetime.fromtimestamp(order.get("timestamp", 0) / 1000, tz=timezone.utc) if order.get("timestamp") else datetime.now(timezone.utc),
            raw_response=order
        )

    def _parse_position(self, pos: Dict) -> PositionInfo:
        """Parse CCXT position to PositionInfo."""
        side = OrderSide.BUY if float(pos.get("contracts", 0)) > 0 else OrderSide.SELL

        return PositionInfo(
            symbol=pos.get("symbol", ""),
            side=side,
            quantity=Decimal(str(abs(float(pos.get("contracts", 0))))),
            entry_price=Decimal(str(pos.get("entryPrice", 0))),
            current_price=Decimal(str(pos.get("markPrice", 0))),
            unrealized_pnl=Decimal(str(pos.get("unrealizedPnl", 0))),
            stop_loss=Decimal(str(pos.get("stopLossPrice", 0))) if pos.get("stopLossPrice") else None,
            take_profit=Decimal(str(pos.get("takeProfitPrice", 0))) if pos.get("takeProfitPrice") else None,
            leverage=Decimal(str(pos.get("leverage", 1))),
            margin=Decimal(str(pos.get("initialMargin", 0))),
            timestamp=datetime.now(timezone.utc)
        )

    def format_symbol(self, symbol: str) -> str:
        """Format symbol for Binance."""
        # Convert BTC/USDT to BTC/USDT (CCXT format)
        return symbol.upper().replace("-", "/")
