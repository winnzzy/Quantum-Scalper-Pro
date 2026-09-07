"""Execution-layer realized P&L accounting regression tests."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.brokers.base import OrderResult
from app.engines.execution import ExecutionEngine
from app.models.trading import BrokerType, TradeDirection, TradeStatus


@pytest.mark.asyncio
async def test_close_trade_deducts_entry_and_exit_commissions(monkeypatch):
    trade = SimpleNamespace(
        id=1,
        user_id=7,
        symbol="TEST/USD",
        direction=TradeDirection.BUY,
        status=TradeStatus.OPEN,
        broker=BrokerType.PAPER,
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        commission=Decimal("1"),
        exit_price=None,
        exit_time=None,
        gross_pnl=None,
        net_pnl=None,
    )
    scalar_result = SimpleNamespace(scalar_one_or_none=lambda: trade)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=scalar_result),
        commit=AsyncMock(),
    )
    broker = SimpleNamespace(
        close_position=AsyncMock(
            return_value=OrderResult(
                success=True,
                filled_price=Decimal("110"),
                commission=Decimal("2"),
            )
        )
    )

    async def get_broker(_broker_type: str, _user_id: int):
        return broker

    monkeypatch.setattr(
        "app.engines.execution.BrokerFactory.get_broker", get_broker
    )
    engine = ExecutionEngine(db, user_id=7)
    engine.risk_engine.update_trade_result = AsyncMock()
    engine.notification_engine.send_trade_notification = AsyncMock()

    result = await engine.close_trade(1)

    assert result["success"] is True
    assert trade.gross_pnl == Decimal("10")
    assert trade.commission == Decimal("3")
    assert trade.net_pnl == Decimal("7")
    engine.risk_engine.update_trade_result.assert_awaited_once_with(
        7, Decimal("7")
    )
