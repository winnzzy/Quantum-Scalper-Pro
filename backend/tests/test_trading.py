"""Trading engine tests."""
import pytest
from decimal import Decimal
from httpx import AsyncClient

from app.main import app
from app.brokers.paper import PaperBroker
from app.brokers.base import BrokerConfig, MarketData, OrderSide, OrderType


@pytest.fixture
async def paper_broker():
    broker = PaperBroker(BrokerConfig())
    await broker.connect()
    yield broker
    await broker.disconnect()


@pytest.mark.asyncio
async def test_paper_broker_connect(paper_broker: PaperBroker):
    """Test paper broker connection."""
    assert paper_broker.is_connected


@pytest.mark.asyncio
async def test_paper_broker_account_info(paper_broker: PaperBroker):
    """Test getting account info."""
    account = await paper_broker.get_account_info()
    assert account.balance > 0
    assert account.equity > 0


@pytest.mark.asyncio
async def test_paper_broker_place_order(paper_broker: PaperBroker):
    """Test placing an order."""
    result = await paper_broker.place_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        stop_loss=Decimal("60000"),
        take_profit=Decimal("70000")
    )
    assert result.success
    assert result.order_id is not None


@pytest.mark.asyncio
async def test_paper_broker_get_positions(paper_broker: PaperBroker):
    """Test getting positions."""
    # Place an order first
    await paper_broker.place_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01")
    )

    positions = await paper_broker.get_positions()
    assert len(positions) > 0


@pytest.mark.asyncio
async def test_paper_broker_close_position(paper_broker: PaperBroker):
    """Test closing a position."""
    # Place and close
    await paper_broker.place_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01")
    )

    result = await paper_broker.close_position("BTC/USDT")
    assert result.success


@pytest.mark.asyncio
async def test_paper_broker_market_data(paper_broker: PaperBroker):
    """Test market data retrieval."""
    data = await paper_broker.get_market_data("BTC/USDT")
    assert data.bid > 0
    assert data.ask > 0
    assert data.ask >= data.bid


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("side", "entry_bid", "entry_ask", "exit_bid", "exit_ask"),
    [
        (OrderSide.BUY, "99", "100", "110", "111"),
        (OrderSide.SELL, "100", "101", "89", "90"),
    ],
)
async def test_paper_round_trip_books_only_pnl_and_commissions(
    paper_broker: PaperBroker,
    monkeypatch,
    side: OrderSide,
    entry_bid: str,
    entry_ask: str,
    exit_bid: str,
    exit_ask: str,
):
    snapshots = iter(
        [
            MarketData(
                symbol="TEST/USD",
                bid=Decimal(entry_bid),
                ask=Decimal(entry_ask),
                last=Decimal(entry_ask if side == OrderSide.BUY else entry_bid),
            ),
            MarketData(
                symbol="TEST/USD",
                bid=Decimal(exit_bid),
                ask=Decimal(exit_ask),
                last=Decimal(exit_bid if side == OrderSide.BUY else exit_ask),
            ),
        ]
    )

    async def fixed_market(_symbol: str):
        return next(snapshots)

    monkeypatch.setattr(paper_broker, "get_market_data", fixed_market)
    opened = await paper_broker.place_order(
        symbol="TEST/USD",
        side=side,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )
    assert opened.success
    closed = await paper_broker.close_position("TEST/USD")
    assert closed.success
    if side == OrderSide.BUY:
        gross_pnl = closed.filled_price - opened.filled_price
    else:
        gross_pnl = opened.filled_price - closed.filled_price
    expected_balance = (
        Decimal("100000")
        + gross_pnl
        - opened.commission
        - closed.commission
    )
    assert (await paper_broker.get_account_info()).balance == expected_balance


@pytest.mark.asyncio
async def test_paper_broker_rejects_invalid_or_duplicate_positions(
    paper_broker: PaperBroker,
):
    invalid = await paper_broker.place_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0"),
    )
    assert invalid.success is False

    first = await paper_broker.place_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
    )
    duplicate = await paper_broker.place_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
    )
    assert first.success
    assert duplicate.success is False
