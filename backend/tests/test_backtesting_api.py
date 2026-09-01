"""Backtesting API regression tests."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.api import api_router
from app.api.v1.backtesting import WalkForwardRequest, run_walk_forward
from app.backtesting.engine import backtest_engine


def test_walk_forward_route_is_registered():
    paths = {route.path for route in api_router.routes}
    assert "/api/v1/backtesting/walk-forward" in paths


def test_walk_forward_request_rejects_reversed_period():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        WalkForwardRequest(
            strategy_name="ema_scalper",
            symbol="BTC/USDT",
            start_date=now,
            end_date=now - timedelta(days=1),
        )


@pytest.mark.asyncio
async def test_walk_forward_endpoint_calls_engine(monkeypatch):
    expected = {
        "out_of_sample_summary": {"validation_status": "promising"}
    }

    async def fake_run_walk_forward(**kwargs):
        assert kwargs["strategy_name"] == "ema_scalper"
        assert kwargs["parameter_candidates"] == [{"min_adx": 20}]
        return expected

    monkeypatch.setattr(
        backtest_engine, "run_walk_forward", fake_run_walk_forward
    )
    request = WalkForwardRequest(
        strategy_name="ema_scalper",
        symbol="BTC/USDT",
        parameter_candidates=[{"min_adx": 20}],
        train_candles=100,
        test_candles=60,
    )

    result = await run_walk_forward(request, current_user=object())

    assert result == expected
