"""Strategy tests."""
import pytest
import pandas as pd
import numpy as np

from app.strategies.ema_scalper import EMAScalper
from app.strategies.vwap_scalper import VWAPScalper
from app.strategies.breakout_scalper import BreakoutScalper
from app.strategies.mean_reversion import MeanReversionScalper
from app.strategies.base import SignalType


def generate_mock_ohlcv(periods=100, trend='up'):
    """Generate mock OHLCV data."""
    np.random.seed(42)
    base = 50000 if trend == 'up' else 50000

    data = []
    for i in range(periods):
        noise = np.random.randn() * 100
        if trend == 'up':
            price = base + i * 10 + noise
        elif trend == 'down':
            price = base - i * 10 + noise
        else:
            price = base + noise

        open_p = price + np.random.randn() * 50
        high_p = max(open_p, price) + abs(np.random.randn()) * 100
        low_p = min(open_p, price) - abs(np.random.randn()) * 100
        close_p = price
        volume = np.random.randint(1000, 10000)

        data.append([int(i), open_p, high_p, low_p, close_p, volume])

    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df


@pytest.mark.asyncio
async def test_ema_scalper_uptrend():
    """Test EMA scalper in uptrend."""
    strategy = EMAScalper()
    df = generate_mock_ohlcv(periods=100, trend='up')

    result = await strategy.analyze("BTC/USDT", df)

    if result:
        assert result.signal.type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
        assert result.signal.confidence >= 0
        assert result.signal.confidence <= 1


@pytest.mark.asyncio
async def test_vwap_scalper():
    """Test VWAP scalper."""
    strategy = VWAPScalper()
    df = generate_mock_ohlcv(periods=100)

    result = await strategy.analyze("BTC/USDT", df)

    if result:
        assert result.signal.symbol == "BTC/USDT"
        assert "vwap" in result.signal.indicators


@pytest.mark.asyncio
async def test_breakout_scalper():
    """Test breakout scalper."""
    strategy = BreakoutScalper()
    df = generate_mock_ohlcv(periods=100)

    result = await strategy.analyze("BTC/USDT", df)

    if result:
        assert "resistance" in result.signal.indicators or "support" in result.signal.indicators


@pytest.mark.asyncio
async def test_mean_reversion():
    """Test mean reversion scalper."""
    strategy = MeanReversionScalper()
    df = generate_mock_ohlcv(periods=100)

    result = await strategy.analyze("BTC/USDT", df)

    if result:
        assert "bb_upper" in result.signal.indicators or "bb_lower" in result.signal.indicators


def test_strategy_registry():
    """Test strategy registry."""
    from app.strategies.registry import StrategyRegistry

    strategies = StrategyRegistry.list_strategies()
    assert "ema_scalper" in strategies
    assert "vwap_scalper" in strategies
    assert "breakout_scalper" in strategies
    assert "mean_reversion" in strategies
