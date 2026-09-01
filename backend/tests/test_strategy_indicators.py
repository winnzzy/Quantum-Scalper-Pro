"""Strategy indicator integrity tests."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.strategies.vwap_scalper import VWAPScalper


def test_vwap_resets_at_each_utc_session():
    day_one = datetime(2026, 1, 1, 23, 58, tzinfo=timezone.utc)
    df = pd.DataFrame({
        "timestamp": [
            day_one,
            day_one + timedelta(minutes=1),
            day_one + timedelta(minutes=2),
        ],
        "open": [100.0, 100.0, 200.0],
        "high": [100.0, 100.0, 200.0],
        "low": [100.0, 100.0, 200.0],
        "close": [100.0, 100.0, 200.0],
        "volume": [10.0, 10.0, 1.0],
    })

    vwap = VWAPScalper().calculate_vwap(df)

    assert vwap.iloc[1] == pytest.approx(100.0)
    assert vwap.iloc[2] == pytest.approx(200.0)


def test_vwap_handles_zero_volume_without_nan_or_infinity():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    df = pd.DataFrame({
        "timestamp": [start, start + timedelta(minutes=1)],
        "open": [100.0, 101.0],
        "high": [100.0, 101.0],
        "low": [100.0, 101.0],
        "close": [100.0, 101.0],
        "volume": [0.0, 0.0],
    })

    vwap = VWAPScalper().calculate_vwap(df)

    assert list(vwap) == pytest.approx([100.0, 101.0])
    assert vwap.notna().all()


def test_adx_identifies_strong_directional_regime():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100.0 + index for index in range(80)]
    df = pd.DataFrame({
        "timestamp": [
            start + timedelta(minutes=index) for index in range(len(closes))
        ],
        "open": [price - 0.25 for price in closes],
        "high": [price + 0.5 for price in closes],
        "low": [price - 0.5 for price in closes],
        "close": closes,
        "volume": [1000.0] * len(closes),
    })

    adx = VWAPScalper().calculate_adx(df, period=14)

    assert adx.iloc[-1] > 25
    assert 0 <= adx.iloc[-1] <= 100
