"""Authenticated API journey across the MVP's critical user workflow."""
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import backtesting, trading
from app.core.database import get_db
from app.main import app


@pytest.fixture
async def e2e_client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(app=app, base_url="http://quantumscalper.pro") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_authenticated_paper_trading_and_validation_journey(
    e2e_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    registration = await e2e_client.post(
        "/api/v1/auth/register",
        json={
            "email": "smoke@example.com",
            "username": "smoke-user",
            "password": "TestPass123!",
        },
    )
    assert registration.status_code == 201

    login = await e2e_client.post(
        "/api/v1/auth/login",
        data={"username": "smoke@example.com", "password": "TestPass123!"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = await e2e_client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "smoke@example.com"

    strategies = await e2e_client.get("/api/v1/strategies/list", headers=headers)
    assert strategies.status_code == 200
    assert "ema_scalper" in strategies.json()["strategies"]

    config = await e2e_client.post(
        "/api/v1/trading/strategies/configs",
        headers=headers,
        json={
            "name": "Smoke EMA",
            "strategy_type": "ema_scalper",
            "parameters": {},
            "symbols": ["BTC/USDT"],
            "timeframes": ["1m"],
            "risk_per_trade": 0.5,
        },
    )
    assert config.status_code == 200
    config_id = config.json()["id"]

    account = await e2e_client.get(
        "/api/v1/trading/account", headers=headers, params={"broker_type": "paper"}
    )
    assert account.status_code == 200
    assert account.json()["balance"] == 100000.0

    start_status = {"is_running": True, "active_tasks": 1, "open_trades": 0}
    stopped_status = {"is_running": False, "active_tasks": 0, "open_trades": 0}
    monkeypatch.setattr(
        trading.trading_engine_manager, "start", AsyncMock(return_value=start_status)
    )
    monkeypatch.setattr(
        trading.trading_engine_manager, "status", AsyncMock(return_value=start_status)
    )
    monkeypatch.setattr(
        trading.trading_engine_manager, "stop", AsyncMock(return_value=stopped_status)
    )

    started = await e2e_client.post(
        "/api/v1/trading/start",
        headers=headers,
        json={"strategy_config_id": config_id},
    )
    assert started.status_code == 200
    assert started.json()["status"]["is_running"] is True
    assert (await e2e_client.get("/api/v1/trading/status", headers=headers)).status_code == 200
    stopped = await e2e_client.post("/api/v1/trading/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"]["is_running"] is False

    walk_forward_result = {
        "status": "promising",
        "summary": {"total_windows": 2, "profitable_windows": 2},
        "windows": [],
        "warnings": ["Reserve a final untouched holdout period."],
    }
    monkeypatch.setattr(
        backtesting.backtest_engine,
        "run_walk_forward",
        AsyncMock(return_value=walk_forward_result),
    )
    validation = await e2e_client.post(
        "/api/v1/backtesting/walk-forward",
        headers=headers,
        json={
            "strategy_name": "ema_scalper",
            "symbol": "BTC/USDT",
            "timeframe": "1m",
            "train_candles": 1000,
            "test_candles": 250,
            "parameter_candidates": [{}],
        },
    )
    assert validation.status_code == 200
    assert validation.json()["status"] == "promising"
