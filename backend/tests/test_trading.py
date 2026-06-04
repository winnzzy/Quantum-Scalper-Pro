"""Trading engine tests."""
import pytest
from decimal import Decimal
from httpx import AsyncClient

from app.main import app
from app.brokers.paper import PaperBroker
from app.brokers.base import BrokerConfig, OrderSide, OrderType


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
