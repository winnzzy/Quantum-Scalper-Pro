"""Execution Engine - Handles order execution across brokers."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BaseBroker, OrderSide, OrderType, OrderResult
from app.brokers.factory import BrokerFactory
from app.core.logging import logger, trade_logger
from app.models.trading import Trade, TradeStatus, TradeDirection, BrokerType
from app.risk.engine import RiskManagementEngine
from app.ai.filter import ai_filter
from app.notifications.engine import NotificationEngine
from app.engines.news import news_filter
from app.core.config import settings
from app.core.hardening import IdempotencyGuard
from app.core.markets import get_market, normalize_symbol, validate_market_broker
from app.core.redis import redis_client
from app.core.operational_state import emergency_stop_active


order_idempotency_guard = IdempotencyGuard(
    redis_client, ttl_seconds=settings.ORDER_IDEMPOTENCY_TTL_SECONDS
)


class ExecutionEngine:
    """
    Execution Engine - Unified order execution for all brokers.

    Handles:
    - Order placement
    - Order tracking
    - Position management
    - Slippage monitoring
    - Execution quality reporting
    """

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self.risk_engine = RiskManagementEngine(db)
        self.notification_engine = NotificationEngine()

    async def execute_signal(
        self,
        signal: Any,  # Signal from strategy
        broker_type: str,
        strategy_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a trading signal.

        Steps:
        1. AI Filter evaluation
        2. Risk validation
        3. News filter check
        4. Order placement
        5. Trade recording
        6. Notification
        """
        result = {
            "success": False,
            "trade_id": None,
            "order_id": None,
            "message": "",
            "risk_check": None,
            "ai_check": None,
            "news_check": None
        }

        symbol = signal.symbol
        direction = signal.type.value
        price = signal.price
        stop_loss = signal.stop_loss
        take_profit = signal.take_profit
        idempotency_key = None

        try:
            symbol = normalize_symbol(symbol)
            validate_market_broker(symbol, broker_type)
            if broker_type != "paper" and not settings.LIVE_TRADING_ENABLED:
                result["message"] = "Live trading is not armed (LIVE_TRADING_ENABLED=false)"
                return result
            if broker_type != "paper" and not redis_client.is_healthy:
                result["message"] = "Live trading blocked: Redis safety state is unavailable"
                return result
            if await emergency_stop_active():
                result["message"] = "Emergency stop is active"
                return result

            # 1. Get broker
            broker = await BrokerFactory.get_broker(broker_type, self.user_id)

            # 2. Get market data for AI filter
            market_data = await broker.get_market_data(symbol)
            spread = market_data.ask - market_data.bid
            quote_error = self._validate_market_data(market_data, broker_type)
            if quote_error:
                result["message"] = f"Market data rejected: {quote_error}"
                logger.warning(f"Market data blocked order for {symbol}: {quote_error}")
                return result

            # 3. AI filter (strategies may explicitly opt out, e.g. manual orders).
            if strategy_config.get("use_ai_filter", True):
                ai_result = ai_filter.evaluate(signal, {
                    "spread": spread,
                    "price": market_data.last,
                })
            else:
                ai_result = {
                    "quality_score": 1.0,
                    "confidence": float(signal.confidence),
                    "recommendation": "pass",
                    "reason": "AI filter disabled for this order",
                    "features": {},
                }
            result["ai_check"] = ai_result

            if ai_result["recommendation"] == "block":
                result["message"] = f"AI Filter blocked: {ai_result['reason']}"
                logger.info(f"Signal blocked by AI: {symbol} {direction}")
                return result

            # 4. Economic-calendar safety gate.
            if strategy_config.get("use_news_filter", True):
                news_result = news_filter.is_news_lock_active(symbol)
            else:
                news_result = {"active": False, "reason": "News filter disabled for strategy"}
            result["news_check"] = news_result

            if news_result["active"]:
                result["message"] = f"News filter blocked: {news_result['reason']}"
                logger.warning(f"Signal blocked by news filter: {symbol} {direction}")
                return result

            # 5. Risk validation
            # Calculate quantity (will be refined by risk engine)
            initial_quantity = Decimal("0.01")  # Placeholder, risk engine will calculate

            risk_result = await self.risk_engine.validate_trade(
                user_id=self.user_id,
                symbol=symbol,
                direction=direction,
                quantity=initial_quantity,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_percent=(
                    Decimal(str(strategy_config["risk_per_trade"]))
                    if strategy_config.get("risk_per_trade") is not None else None
                ),
                broker_type=broker_type
            )
            result["risk_check"] = risk_result

            if not risk_result["allowed"]:
                result["message"] = f"Risk check failed: {risk_result['reason']}"
                logger.warning(f"Trade blocked by risk: {symbol} {direction} - {risk_result['reason']}")
                return result

            signal_id = self._signal_fingerprint(signal, strategy_config)
            allowed, idempotency_key = await order_idempotency_guard.check_and_reserve(
                self.user_id, signal_id, symbol
            )
            if not allowed:
                result["message"] = "Duplicate signal rejected"
                return result

            # 6. Place order
            order_side = OrderSide.BUY if direction == "buy" else OrderSide.SELL
            order_type = OrderType.MARKET  # Default to market for scalping

            order_result = await broker.place_order(
                symbol=symbol,
                side=order_side,
                order_type=order_type,
                quantity=risk_result["position_size"],
                price=price if order_type == OrderType.LIMIT else None,
                stop_loss=risk_result.get("adjusted_stop_loss") or stop_loss,
                take_profit=take_profit
            )

            if not order_result.success:
                await order_idempotency_guard.mark_failed(idempotency_key)
                result["message"] = f"Order failed: {order_result.error_message}"
                logger.error(f"Order execution failed: {order_result.error_message}")
                return result

            # 7. Record trade
            trade = Trade(
                user_id=self.user_id,
                symbol=symbol,
                direction=TradeDirection.BUY if direction == "buy" else TradeDirection.SELL,
                status=TradeStatus.OPEN,
                entry_price=order_result.filled_price or price,
                entry_time=datetime.now(timezone.utc),
                quantity=risk_result["position_size"],
                stop_loss=risk_result.get("adjusted_stop_loss") or stop_loss,
                take_profit=take_profit,
                risk_percent=Decimal(str(strategy_config.get("risk_per_trade"))) if strategy_config.get("risk_per_trade") is not None else None,
                risk_amount=risk_result["risk_amount"],
                strategy_name=strategy_config.get("strategy_type", "unknown"),
                strategy_config=strategy_config,
                ai_confidence=Decimal(str(ai_result["confidence"])),
                ai_quality_score=Decimal(str(ai_result["quality_score"])),
                broker=BrokerType(broker_type) if broker_type in [e.value for e in BrokerType] else BrokerType.PAPER,
                broker_trade_id=order_result.order_id,
                broker_order_id=order_result.order_id,
                commission=order_result.commission or Decimal("0"),
            )

            self.db.add(trade)
            await self.db.commit()
            await self.db.refresh(trade)
            await order_idempotency_guard.mark_completed(idempotency_key, trade.id)

            # 8. Send notification
            await self.notification_engine.send_trade_notification(
                self.user_id,
                "trade_open",
                trade
            )

            result["success"] = True
            result["trade_id"] = trade.id
            result["order_id"] = order_result.order_id
            result["message"] = f"Trade executed: {symbol} {direction} @ {order_result.filled_price or price}"

            trade_logger.info(
                f"TRADE EXECUTED: ID {trade.id} | {symbol} {direction} | "
                f"Qty: {risk_result['position_size']} | Price: {order_result.filled_price or price} | "
                f"SL: {trade.stop_loss} | TP: {trade.take_profit}"
            )

            return result

        except Exception as e:
            logger.error(f"Execution error: {e}")
            result["message"] = f"Execution error: {str(e)}"
            return result

    @staticmethod
    def _signal_fingerprint(signal: Any, strategy_config: Dict[str, Any]) -> str:
        """Build a stable identity for one strategy/candle/direction decision."""
        timestamp = getattr(signal, "timestamp", None)
        payload = {
            "strategy": strategy_config.get("strategy_type", "unknown"),
            "symbol": normalize_symbol(signal.symbol),
            "direction": signal.type.value,
            "timeframe": getattr(signal, "timeframe", "1m"),
            "timestamp": timestamp.isoformat() if timestamp else None,
            "price": str(signal.price),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:32]

    @staticmethod
    def _validate_market_data(market_data: Any, broker_type: str) -> Optional[str]:
        if market_data.bid <= 0 or market_data.ask <= 0 or market_data.last <= 0:
            return "non-positive quote"
        if market_data.ask < market_data.bid:
            return "crossed quote"
        if broker_type != "paper":
            if market_data.timestamp is None:
                return "live quote has no timestamp"
            quote_time = market_data.timestamp
            if quote_time.tzinfo is None:
                quote_time = quote_time.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - quote_time.astimezone(timezone.utc)).total_seconds()
            if age < -5 or age > settings.MAX_MARKET_DATA_AGE_SECONDS:
                return f"stale quote ({age:.1f}s old)"
            spread_fraction = (market_data.ask - market_data.bid) / market_data.last
            if spread_fraction > Decimal(str(get_market(market_data.symbol).max_live_spread_pct)):
                return f"spread too wide ({float(spread_fraction) * 100:.4f}%)"
        return None

    async def close_trade(self, trade_id: int, exit_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """Close an open trade."""
        result = {"success": False, "message": ""}

        try:
            from sqlalchemy import select
            trade_result = await self.db.execute(
                select(Trade).where(Trade.id == trade_id, Trade.user_id == self.user_id)
            )
            trade = trade_result.scalar_one_or_none()

            if not trade or trade.status != TradeStatus.OPEN:
                result["message"] = "Trade not found or not open"
                return result

            # Get broker
            broker = await BrokerFactory.get_broker(trade.broker.value, self.user_id)

            # Close position
            close_result = await broker.close_position(
                trade.symbol,
                OrderSide.SELL if trade.direction == TradeDirection.BUY else OrderSide.BUY
            )

            if not close_result.success:
                result["message"] = f"Close failed: {close_result.error_message}"
                return result

            # Calculate P&L
            if trade.direction == TradeDirection.BUY:
                pnl = (close_result.filled_price - trade.entry_price) * trade.quantity
            else:
                pnl = (trade.entry_price - close_result.filled_price) * trade.quantity

            # Update trade
            trade.status = TradeStatus.CLOSED
            trade.exit_price = close_result.filled_price
            trade.exit_time = datetime.now(timezone.utc)
            trade.gross_pnl = pnl
            exit_commission = close_result.commission or Decimal("0")
            entry_commission = trade.commission or Decimal("0")
            trade.net_pnl = pnl - entry_commission - exit_commission
            trade.commission = entry_commission + exit_commission

            await self.db.commit()

            # Update risk engine
            await self.risk_engine.update_trade_result(self.user_id, trade.net_pnl)

            # Send notification
            await self.notification_engine.send_trade_notification(
                self.user_id,
                "trade_close",
                trade
            )

            result["success"] = True
            result["message"] = f"Trade closed: P&L {trade.net_pnl}"

            trade_logger.info(
                f"TRADE CLOSED: ID {trade.id} | {trade.symbol} | "
                f"P&L: {trade.net_pnl} | Exit: {close_result.filled_price}"
            )

            return result

        except Exception as e:
            logger.error(f"Close trade error: {e}")
            result["message"] = f"Close error: {str(e)}"
            return result

    async def check_stop_loss_take_profit(self, trade: Trade, current_price: Decimal) -> bool:
        """Check if stop loss or take profit hit."""
        if trade.status != TradeStatus.OPEN:
            return False

        sl_hit = False
        tp_hit = False

        if trade.stop_loss:
            if trade.direction == TradeDirection.BUY and current_price <= trade.stop_loss:
                sl_hit = True
            elif trade.direction == TradeDirection.SELL and current_price >= trade.stop_loss:
                sl_hit = True

        if trade.take_profit:
            if trade.direction == TradeDirection.BUY and current_price >= trade.take_profit:
                tp_hit = True
            elif trade.direction == TradeDirection.SELL and current_price <= trade.take_profit:
                tp_hit = True

        if sl_hit or tp_hit:
            reason = "stop_loss" if sl_hit else "take_profit"
            result = await self.close_trade(trade.id, current_price)

            if result["success"]:
                await self.notification_engine.send_trade_notification(
                    self.user_id,
                    f"{reason}_hit",
                    trade
                )

            return True

        return False
