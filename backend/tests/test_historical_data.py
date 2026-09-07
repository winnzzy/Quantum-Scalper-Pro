"""Historical data quality and provenance tests."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.backtesting.data import (
    HistoricalDataValidationError,
    import_ohlcv_csv,
    validate_ohlcv_frame,
)
from app.backtesting.engine import BacktestingEngine


def market_frame(rows: int = 60) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return pd.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=i) for i in range(rows)],
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.5] * rows,
            "volume": [1000.0] * rows,
        }
    )


def test_valid_frame_reports_chronology_and_gaps():
    frame = market_frame()
    frame.loc[30:, "timestamp"] += timedelta(minutes=2)

    validated, report = validate_ohlcv_frame(frame, "1m")

    assert len(validated) == 60
    assert report.missing_intervals == 2
    assert report.gap_rate_pct > 0


@pytest.mark.parametrize("corruption", ["duplicate", "negative", "invalid_high"])
def test_corrupt_market_data_is_rejected(corruption: str):
    frame = market_frame()
    if corruption == "duplicate":
        frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    elif corruption == "negative":
        frame.loc[1, "close"] = -100
    else:
        frame.loc[1, "high"] = 98

    with pytest.raises(HistoricalDataValidationError):
        validate_ohlcv_frame(frame, "1m")


def test_import_writes_canonical_data_and_fingerprinted_manifest(tmp_path):
    input_path = tmp_path / "vendor.csv"
    market_frame().to_csv(input_path, index=False)

    data_path, manifest_path, report = import_ohlcv_csv(
        input_path,
        tmp_path / "historical",
        "BTC/USDT",
        "1m",
        "exchange export",
        min_rows=50,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert report.rows == 60
    assert manifest["source"] == "exchange export"
    assert manifest["sha256"] == hashlib.sha256(data_path.read_bytes()).hexdigest()


@pytest.mark.asyncio
async def test_backtest_returns_bounded_error_for_corrupt_file(tmp_path):
    frame = market_frame()
    frame.loc[1, "high"] = 98
    frame.to_csv(tmp_path / "BTC_USDT_1m.csv", index=False)
    engine = BacktestingEngine()
    engine.data_path = tmp_path

    result = await engine.run("ema_scalper", "BTC/USDT", "1m")

    assert result == {
        "error": "Historical data validation failed: OHLC invariants fail in 1 rows"
    }
