"""Backtest integrity regression tests."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest

from app.backtesting.engine import BacktestPosition, BacktestingEngine, RiskState
from app.strategies.breakout_scalper import BreakoutScalper
from app.strategies.base import SignalType


def test_execution_costs_are_subtracted_once():
    engine = BacktestingEngine()
    position = BacktestPosition(
        symbol="BTC/USDT",
        side="buy",
        entry_price=Decimal("100.06"),
        entry_reference_price=Decimal("100"),
        quantity=Decimal("1"),
        entry_commission=Decimal("0.04"),
        entry_slippage_cost=Decimal("0.01"),
        entry_spread_cost=Decimal("0.05"),
    )

    trade = engine._close_position(
        position=position,
        exit_price_raw=Decimal("110"),
        exit_time=datetime.now(timezone.utc),
        exit_reason="test",
        commission_rate=Decimal("0.0004"),
        slippage_rate=Decimal("0.0001"),
        spread=Decimal("0.001"),
    )

    assert trade.gross_pnl == Decimal("10")
    assert trade.net_pnl == (
        trade.gross_pnl
        - trade.commission
        - trade.slippage_cost
        - trade.spread_cost
    )


def test_daily_loss_lock_resets_on_new_utc_day():
    engine = BacktestingEngine()
    state = RiskState(
        balance=Decimal("100000"),
        peak_equity=Decimal("100000"),
        daily_start_balance=Decimal("100000"),
    )
    first_day = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    engine._roll_risk_day(state, first_day)
    state.daily_pnl = Decimal("4000")
    state.daily_locked = True

    engine._roll_risk_day(state, first_day + timedelta(days=1))

    assert state.daily_pnl == 0
    assert state.daily_locked is False
    assert state.daily_start_balance == state.balance


@pytest.mark.asyncio
async def test_breakout_uses_prior_resistance():
    rows = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(39):
        rows.append({
            "timestamp": start + timedelta(minutes=index),
            "open": 99.5,
            "high": 100.0,
            "low": 99.0,
            "close": 99.8,
            "volume": 1000.0,
        })
    rows.append({
        "timestamp": start + timedelta(minutes=39),
        "open": 99.8,
        "high": 101.5,
        "low": 99.7,
        "close": 101.2,
        "volume": 2500.0,
    })

    result = await BreakoutScalper().analyze("BTC/USDT", pd.DataFrame(rows))

    assert result is not None
    assert result.signal.type == SignalType.BUY


def test_stop_loss_gap_exits_at_open():
    engine = BacktestingEngine()
    position = BacktestPosition(
        symbol="BTC/USDT",
        side="buy",
        entry_price=Decimal("100"),
        entry_reference_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
    )

    trade = engine._check_sl_tp(
        position=position,
        candle_open=Decimal("90"),
        candle_high=Decimal("92"),
        candle_low=Decimal("89"),
        spread=Decimal("0"),
        commission_rate=Decimal("0"),
        slippage_rate=Decimal("0"),
        candle_time=datetime.now(timezone.utc),
        symbol="BTC/USDT",
    )

    assert trade is not None
    assert trade.exit_reason == "stop_loss_gap"
    assert trade.exit_price == Decimal("90.00000000")


def test_ambiguous_intrabar_exit_uses_stop_loss():
    engine = BacktestingEngine()
    position = BacktestPosition(
        symbol="BTC/USDT",
        side="buy",
        entry_price=Decimal("100"),
        entry_reference_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("105"),
    )

    trade = engine._check_sl_tp(
        position=position,
        candle_open=Decimal("100"),
        candle_high=Decimal("106"),
        candle_low=Decimal("94"),
        spread=Decimal("0"),
        commission_rate=Decimal("0"),
        slippage_rate=Decimal("0"),
        candle_time=datetime.now(timezone.utc),
        symbol="BTC/USDT",
    )

    assert trade is not None
    assert trade.exit_reason == "ambiguous_stop_loss"
    assert trade.exit_price == Decimal("95.00000000")
    assert trade.net_pnl == Decimal("-5")


@pytest.mark.asyncio
async def test_walk_forward_selects_on_train_and_reports_unseen_windows(monkeypatch):
    engine = BacktestingEngine()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(200):
        price = 100.0 + index * 0.01
        rows.append({
            "timestamp": start + timedelta(minutes=index),
            "open": price,
            "high": price + 0.1,
            "low": price - 0.1,
            "close": price,
            "volume": 1000.0,
        })
    frame = pd.DataFrame(rows)
    calls = []

    async def fake_load(*args, **kwargs):
        return frame

    async def fake_run(**kwargs):
        calls.append(kwargs)
        preferred = kwargs["parameters"].get("variant") == "stable"
        return {
            "total_trades": 12,
            "winning_trades": 8 if preferred else 5,
            "losing_trades": 4 if preferred else 7,
            "win_rate": 66.67 if preferred else 41.67,
            "gross_profit": 240.0 if preferred else 100.0,
            "gross_loss": 100.0,
            "net_pnl": 140.0 if preferred else 0.0,
            "profit_factor": 2.4 if preferred else 1.0,
            "sharpe_ratio": 1.5 if preferred else 0.1,
            "sortino_ratio": 1.8 if preferred else 0.1,
            "max_drawdown_pct": 4.0 if preferred else 9.0,
        }

    monkeypatch.setattr(engine, "_load_data", fake_load)
    monkeypatch.setattr(engine, "run", fake_run)

    result = await engine.run_walk_forward(
        strategy_name="ema_scalper",
        symbol="BTC/USDT",
        parameter_candidates=[
            {"variant": "unstable"},
            {"variant": "stable"},
        ],
        train_candles=80,
        test_candles=60,
        step_candles=60,
    )

    assert len(result["windows"]) == 2
    assert all(
        window["selected_parameters"] == {"variant": "stable"}
        for window in result["windows"]
    )
    assert all(
        pd.Timestamp(window["train_period"]["end"])
        < pd.Timestamp(window["test_period"]["start"])
        for window in result["windows"]
    )
    assert result["out_of_sample_summary"]["window_count"] == 2
    assert result["out_of_sample_summary"]["validation_status"] == (
        "insufficient_evidence"
    )
    assert len(calls) == 6
