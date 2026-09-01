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
