"""Trading Engine - Main orchestrator for trading operations."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.core.logging import logger
from app.models.trading import Trade, TradeStatus, StrategyConfig
from app.models.user import User
from app.strategies.registry import StrategyRegistry
from app.brokers.factory import BrokerFactory
from app.engines.execution import ExecutionEngine
from app.risk.engine import RiskManagementEngine
from app.ai.filter import ai_filter
from app.core.redis import redis_client


class TradingEngine:
    """
    Trading Engine - Main orchestrator.

    Responsibilities:
    - Strategy execution loop
    - Market data fetching
    - Signal generation
    - Trade management
    - Position monitoring
    """

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self.execution_engine = ExecutionEngine(db, user_id)
        self.risk_engine = RiskManagementEngine(db)
        self.is_running = False
        self._tasks: List[asyncio.Task] = []

    async def start(self, strategy_configs: List[Dict[str, Any]]):
        """Start trading engine with strategies."""
        if self.is_running:
            logger.warning("Trading engine already running")
            return

        self.is_running = True
        logger.info(f"Trading engine started for user {self.user_id}")

        # Create tasks for each strategy
        for config in strategy_configs:
            if config.get("is_active", True):
                task = asyncio.create_task(
                    self._strategy_loop(config),
                    name=f"strategy_{config['strategy_type']}_{self.user_id}"
                )
                self._tasks.append(task)

        # Position monitoring task
        monitor_task = asyncio.create_task(
            self._position_monitor(),
            name=f"monitor_{self.user_id}"
        )
        self._tasks.append(monitor_task)

    async def stop(self):
        """Stop trading engine."""
        self.is_running = False

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()
        logger.info(f"Trading engine stopped for user {self.user_id}")

    async def _strategy_loop(self, config: Dict[str, Any]):
        """Main strategy execution loop."""
        strategy_type = config["strategy_type"]
        symbols = config.get("symbols", ["BTC/USDT"])
        timeframe = config.get("timeframe", "1m")
        broker_type = config.get("broker_type", "paper")

        try:
            strategy = StrategyRegistry.get_strategy(strategy_type, config.get("parameters", {}))
        except Exception as e:
            logger.error(f"Failed to load strategy {strategy_type}: {e}")
            return

        broker = await BrokerFactory.get_broker(broker_type, self.user_id)

        while self.is_running:
            try:
                for symbol in symbols:
                    if not self.is_running:
                        break

                    # Fetch market data
                    ohlcv = await broker.get_ohlcv(symbol, timeframe, limit=100)

                    if not ohlcv or len(ohlcv) < 50:
                        logger.warning(f"Insufficient data for {symbol}")
                        continue

                    # Convert to DataFrame
                    df = pd.DataFrame(
                        ohlcv,
                        columns=["timestamp", "open", "high", "low", "close", "volume"]
                    )

                    # Analyze
                    result = await strategy.analyze(symbol, df)

                    if result and result.signal.type.value in ["buy", "sell"]:
                        logger.info(
                            f"Signal generated: {symbol} {result.signal.type.value} "
                            f"(confidence: {result.signal.confidence:.2f})"
                        )

                        # Execute
                        exec_result = await self.execution_engine.execute_signal(
                            result.signal,
                            broker_type,
                            config
                        )

                        if exec_result["success"]:
                            logger.info(f"Trade executed: {exec_result['trade_id']}")
                        else:
                            logger.warning(f"Trade failed: {exec_result['message']}")

                # Wait before next iteration
                await asyncio.sleep(60)  # 1 minute for scalping

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Strategy loop error: {e}")
                await asyncio.sleep(60)

    async def _position_monitor(self):
        """Monitor open positions for SL/TP hits."""
        while self.is_running:
            try:
                # Get open trades
                result = await self.db.execute(
                    select(Trade).where(
                        and_(
                            Trade.user_id == self.user_id,
                            Trade.status == TradeStatus.OPEN
                        )
                    )
                )
                trades = result.scalars().all()

                for trade in trades:
                    try:
                        # Get current price
                        broker = await BrokerFactory.get_broker(trade.broker.value, self.user_id)
                        market_data = await broker.get_market_data(trade.symbol)
                        current_price = market_data.last

                        # Check SL/TP
                        await self.execution_engine.check_stop_loss_take_profit(trade, current_price)

                    except Exception as e:
                        logger.error(f"Position monitor error for trade {trade.id}: {e}")

                await asyncio.sleep(5)  # Check every 5 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Position monitor error: {e}")
                await asyncio.sleep(5)

    async def get_status(self) -> Dict[str, Any]:
        """Get trading engine status."""
        result = await self.db.execute(
            select(Trade).where(
                and_(
                    Trade.user_id == self.user_id,
                    Trade.status == TradeStatus.OPEN
                )
            )
        )
        open_trades = len(result.scalars().all())

        return {
            "is_running": self.is_running,
            "active_tasks": len(self._tasks),
            "open_trades": open_trades,
            "user_id": self.user_id
        }
