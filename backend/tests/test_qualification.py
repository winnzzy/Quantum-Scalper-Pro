"""Tests for untouched holdouts and dataset-bound live promotion."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.backtesting.engine import BacktestingEngine
from app.backtesting.evidence import qualification_readiness, save_qualification
from app.backtesting.presets import get_validation_preset
from app.core.config import settings


def _metrics() -> dict:
    return {
        "total_trades": 12, "winning_trades": 7, "losing_trades": 5,
        "win_rate": 58.33, "gross_profit": 2400.0, "gross_loss": 1000.0,
        "net_pnl": 1400.0, "profit_factor": 2.4, "sharpe_ratio": 1.3,
        "sortino_ratio": 1.8, "max_drawdown_pct": 4.0,
    }


@pytest.mark.asyncio
async def test_walk_forward_reserves_and_stresses_untouched_holdout(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "BACKTEST_DATA_PATH", str(tmp_path))
    engine = BacktestingEngine()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    frame = pd.DataFrame({
        "timestamp": [start + timedelta(minutes=5 * index) for index in range(400)],
        "open": [100.0] * 400, "high": [101.0] * 400,
        "low": [99.0] * 400, "close": [100.0] * 400,
        "volume": [1000.0] * 400,
    })

    async def fake_load(*args, **kwargs):
        return frame

    async def fake_run(*args, **kwargs):
        return _metrics()

    monkeypatch.setattr(engine, "_load_data", fake_load)
    monkeypatch.setattr(engine, "run", fake_run)
    result = await engine.run_walk_forward(
        "dual_market_regime", "BTC/USDT", "5m",
        parameter_candidates=[{"min_adx": 22}], train_candles=100,
        test_candles=60, step_candles=60, holdout_candles=100,
        min_train_trades=5, spread_pct=0.0002,
        commission_rate=0.0004, slippage_rate=0.0001,
    )

    assert len(result["windows"]) == 3
    assert result["windows"][-1]["test_period"]["end"] < result["untouched_holdout"]["period"]["start"]
    assert result["adverse_cost_holdout"]["cost_multipliers"]["slippage"] == 2.0
    assert result["promotion_gate"]["approved"] is True


def test_qualification_is_bound_to_exact_dataset(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "BACKTEST_DATA_PATH", str(tmp_path))
    data = tmp_path / "BTC_USDT_5m.csv"
    data.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    (tmp_path / "BTC_USDT_5m.manifest.json").write_text(
        json.dumps({"sha256": digest, "source": "verified fixture"}), encoding="utf-8"
    )
    result = {
        "strategy": "dual_market_regime", "final_parameters": {"min_adx": 22},
        "promotion_gate": {"approved": True},
    }
    save_qualification("BTC/USDT", "5m", result)
    assert qualification_readiness("BTC/USDT", "5m")["ready_for_live"] is True

    data.write_text("tampered", encoding="utf-8")
    readiness = qualification_readiness("BTC/USDT", "5m")
    assert readiness["ready_for_live"] is False
    assert any("fingerprint" in blocker for blocker in readiness["blockers"])


def test_asset_presets_are_bounded_and_isolated():
    btc = get_validation_preset("BTCUSD")
    gold = get_validation_preset("GOLD")
    assert btc["strategy_name"] == gold["strategy_name"] == "dual_market_regime"
    assert btc["parameter_candidates"] != gold["parameter_candidates"]
    assert len(btc["parameter_candidates"]) == 3
    btc["parameter_candidates"].clear()
    assert len(get_validation_preset("BTC/USDT")["parameter_candidates"]) == 3
