from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.brokers.base import MarketData
from app.engines.execution import ExecutionEngine


def quote(timestamp=None, bid="100", ask="100.01", last="100"):
    return MarketData(
        symbol="BTC/USDT",
        bid=Decimal(bid),
        ask=Decimal(ask),
        last=Decimal(last),
        timestamp=timestamp,
    )


def test_rejects_crossed_and_non_positive_quotes():
    assert ExecutionEngine._validate_market_data(quote(bid="101", ask="100"), "paper") == "crossed quote"
    assert ExecutionEngine._validate_market_data(quote(last="0"), "paper") == "non-positive quote"


def test_live_quote_must_be_fresh_and_tight():
    stale = datetime.now(timezone.utc) - timedelta(minutes=2)
    assert "stale quote" in ExecutionEngine._validate_market_data(quote(stale), "binance_testnet")
    now = datetime.now(timezone.utc)
    assert "spread too wide" in ExecutionEngine._validate_market_data(
        quote(now, bid="99", ask="101", last="100"), "binance_testnet"
    )
    assert ExecutionEngine._validate_market_data(quote(now), "binance_testnet") is None
