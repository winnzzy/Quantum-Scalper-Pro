"""Trading runtime and per-user engine lifecycle management."""
import asyncio
from typing import Any, Dict, List

import pandas as pd
from sqlalchemy import and_, select

from app.brokers.factory import BrokerFactory
from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.engines.execution import ExecutionEngine
from app.models.trading import Trade, TradeStatus
from app.strategies.registry import StrategyRegistry


class TradingEngine:
    """Run strategy and position-monitor tasks for one user."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.is_running = False
        self._tasks: List[asyncio.Task] = []

    async def start(self, strategy_configs: List[Dict[str, Any]]):
        if self.is_running:
            raise RuntimeError("Trading engine is already running")
        active_configs = [config for config in strategy_configs if config.get("is_active", True)]
        if not active_configs:
            raise ValueError("At least one active strategy configuration is required")

        self.is_running = True
        for config in active_configs:
            task = asyncio.create_task(
                self._strategy_loop(config),
                name=f"strategy_{config['strategy_type']}_{self.user_id}",
            )
            self._tasks.append(task)

        self._tasks.append(
            asyncio.create_task(
                self._position_monitor(),
                name=f"monitor_{self.user_id}",
            )
        )
        logger.info(f"Trading engine started for user {self.user_id}")

    async def stop(self):
        if not self.is_running and not self._tasks:
            return
        self.is_running = False
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"Trading engine stopped for user {self.user_id}")

    async def _strategy_loop(self, config: Dict[str, Any]):
        strategy_type = config["strategy_type"]
        symbols = config.get("symbols") or ["BTC/USDT"]
        timeframes = config.get("timeframes") or [config.get("timeframe", "1m")]
        timeframe = timeframes[0]
        broker_type = config.get("broker_type", "paper")
        interval_seconds = max(5, int(config.get("interval_seconds", 60)))

        try:
            strategy = StrategyRegistry.get_strategy(strategy_type, config.get("parameters", {}))
            broker = await BrokerFactory.get_broker(broker_type, self.user_id)
        except Exception as exc:
            logger.error(f"Failed to initialize strategy {strategy_type}: {exc}")
            self.is_running = False
            return

        while self.is_running:
            try:
                for symbol in symbols:
                    if not self.is_running:
                        break
                    ohlcv = await broker.get_ohlcv(symbol, timeframe, limit=200)
                    if not ohlcv or len(ohlcv) < 50:
                        logger.warning(f"Insufficient data for {symbol} on {timeframe}")
                        continue

                    frame = pd.DataFrame(
                        ohlcv,
                        columns=["timestamp", "open", "high", "low", "close", "volume"],
                    )
                    result = await strategy.analyze(symbol, frame)
                    if not result or result.signal.type.value not in {"buy", "sell"}:
                        continue

                    async with AsyncSessionLocal() as session:
                        execution = ExecutionEngine(session, self.user_id)
                        execution_result = await execution.execute_signal(
                            result.signal,
                            broker_type,
                            config,
                        )
                    if execution_result["success"]:
                        logger.info(f"Trade executed: {execution_result['trade_id']}")
                    else:
                        logger.warning(f"Trade rejected: {execution_result['message']}")

                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Strategy loop error for user {self.user_id}: {exc}")
                await asyncio.sleep(interval_seconds)

    async def _position_monitor(self):
        while self.is_running:
            try:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(Trade).where(
                            and_(
                                Trade.user_id == self.user_id,
                                Trade.status == TradeStatus.OPEN,
                            )
                        )
                    )
                    trades = result.scalars().all()
                    execution = ExecutionEngine(session, self.user_id)

                    for trade in trades:
                        broker = await BrokerFactory.get_broker(trade.broker.value, self.user_id)
                        market_data = await broker.get_market_data(trade.symbol)
                        await execution.check_stop_loss_take_profit(trade, market_data.last)

                await asyncio.sleep(5)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Position monitor error for user {self.user_id}: {exc}")
                await asyncio.sleep(5)

    async def get_status(self) -> Dict[str, Any]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Trade.id).where(
                    and_(
                        Trade.user_id == self.user_id,
                        Trade.status == TradeStatus.OPEN,
                    )
                )
            )
            open_trades = len(result.scalars().all())

        active_tasks = sum(not task.done() for task in self._tasks)
        return {
            "is_running": self.is_running and active_tasks > 0,
            "active_tasks": active_tasks,
            "open_trades": open_trades,
            "user_id": self.user_id,
        }


class TradingEngineManager:
    """Own the single live engine instance for each user in this process."""

    def __init__(self):
        self._engines: Dict[int, TradingEngine] = {}
        self._lock = asyncio.Lock()

    async def start(self, user_id: int, configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        async with self._lock:
            existing = self._engines.get(user_id)
            if existing and existing.is_running:
                raise RuntimeError("Trading engine is already running")
            if existing:
                await existing.stop()

            engine = TradingEngine(user_id)
            await engine.start(configs)
            self._engines[user_id] = engine
            return await engine.get_status()

    async def stop(self, user_id: int) -> Dict[str, Any]:
        async with self._lock:
            engine = self._engines.pop(user_id, None)
            if engine:
                await engine.stop()
            return await self.status(user_id)

    async def status(self, user_id: int) -> Dict[str, Any]:
        engine = self._engines.get(user_id)
        if engine:
            return await engine.get_status()
        return await TradingEngine(user_id).get_status()

    async def stop_all(self):
        async with self._lock:
            engines, self._engines = list(self._engines.values()), {}
        await asyncio.gather(*(engine.stop() for engine in engines), return_exceptions=True)


trading_engine_manager = TradingEngineManager()
