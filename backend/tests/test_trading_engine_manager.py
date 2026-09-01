"""Trading engine lifecycle manager tests."""
import pytest

import app.engines.trading as trading_module
from app.engines.trading import TradingEngineManager


class FakeEngine:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.is_running = False
        self.stopped = False

    async def start(self, configs):
        if not configs:
            raise ValueError("configs required")
        self.is_running = True

    async def stop(self):
        self.is_running = False
        self.stopped = True

    async def get_status(self):
        return {
            "is_running": self.is_running,
            "active_tasks": 1 if self.is_running else 0,
            "open_trades": 0,
            "user_id": self.user_id,
        }


@pytest.mark.asyncio
async def test_manager_controls_same_user_engine(monkeypatch):
    monkeypatch.setattr(trading_module, "TradingEngine", FakeEngine)
    manager = TradingEngineManager()

    started = await manager.start(7, [{"strategy_type": "ema_scalper"}])
    assert started["is_running"] is True
    assert (await manager.status(7))["is_running"] is True

    stopped = await manager.stop(7)
    assert stopped["is_running"] is False


@pytest.mark.asyncio
async def test_manager_rejects_duplicate_start(monkeypatch):
    monkeypatch.setattr(trading_module, "TradingEngine", FakeEngine)
    manager = TradingEngineManager()
    await manager.start(9, [{"strategy_type": "ema_scalper"}])

    with pytest.raises(RuntimeError, match="already running"):
        await manager.start(9, [{"strategy_type": "vwap_scalper"}])

    await manager.stop_all()
