"""Strict historical-market-data validation and canonical import utilities."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class HistoricalDataValidationError(ValueError):
    """Raised when OHLCV data cannot safely be used for performance claims."""


@dataclass(frozen=True)
class DataQualityReport:
    rows: int
    start: str
    end: str
    duplicate_timestamps: int
    missing_intervals: int
    gap_rate_pct: float
    timeframe: str


def validate_ohlcv_frame(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    min_rows: int = 50,
    max_gap_rate_pct: Optional[float] = None,
) -> tuple[pd.DataFrame, DataQualityReport]:
    """Validate OHLCV without mutating or silently repairing market prices."""
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame]
    if missing_columns:
        raise HistoricalDataValidationError(
            f"Missing required columns: {', '.join(missing_columns)}"
        )
    if timeframe not in TIMEFRAME_MINUTES:
        raise HistoricalDataValidationError(f"Unsupported timeframe: {timeframe}")

    data = frame.loc[:, REQUIRED_COLUMNS].copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True, errors="coerce")
    for column in REQUIRED_COLUMNS[1:]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    null_counts = data.isna().sum()
    invalid_nulls = {key: int(value) for key, value in null_counts.items() if value}
    if invalid_nulls:
        raise HistoricalDataValidationError(
            f"Null or non-numeric values found: {invalid_nulls}"
        )
    if len(data) < min_rows:
        raise HistoricalDataValidationError(
            f"At least {min_rows} candles are required; received {len(data)}"
        )

    duplicates = int(data["timestamp"].duplicated().sum())
    if duplicates:
        raise HistoricalDataValidationError(
            f"Duplicate timestamps found: {duplicates}"
        )
    if not data["timestamp"].is_monotonic_increasing:
        raise HistoricalDataValidationError(
            "Timestamps must be strictly chronological"
        )

    non_positive = (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
    if non_positive.any():
        raise HistoricalDataValidationError(
            f"Non-positive OHLC prices found in {int(non_positive.sum())} rows"
        )
    if (data["volume"] < 0).any():
        raise HistoricalDataValidationError(
            f"Negative volume found in {int((data['volume'] < 0).sum())} rows"
        )

    invalid_high = data["high"] < data[["open", "close", "low"]].max(axis=1)
    invalid_low = data["low"] > data[["open", "close", "high"]].min(axis=1)
    invalid_ohlc = invalid_high | invalid_low
    if invalid_ohlc.any():
        raise HistoricalDataValidationError(
            f"OHLC invariants fail in {int(invalid_ohlc.sum())} rows"
        )

    expected_seconds = TIMEFRAME_MINUTES[timeframe] * 60
    deltas = data["timestamp"].diff().dt.total_seconds().dropna()
    irregular = deltas[deltas < expected_seconds]
    if not irregular.empty:
        raise HistoricalDataValidationError(
            f"Intervals shorter than {timeframe} found in {len(irregular)} rows"
        )
    missing_intervals = int(
        sum(max(round(delta / expected_seconds) - 1, 0) for delta in deltas)
    )
    expected_total = len(data) + missing_intervals
    gap_rate = (missing_intervals / expected_total * 100) if expected_total else 0.0
    if max_gap_rate_pct is not None and gap_rate > max_gap_rate_pct:
        raise HistoricalDataValidationError(
            f"Gap rate {gap_rate:.4f}% exceeds limit {max_gap_rate_pct:.4f}%"
        )

    report = DataQualityReport(
        rows=len(data),
        start=data["timestamp"].iloc[0].isoformat(),
        end=data["timestamp"].iloc[-1].isoformat(),
        duplicate_timestamps=duplicates,
        missing_intervals=missing_intervals,
        gap_rate_pct=round(gap_rate, 6),
        timeframe=timeframe,
    )
    return data, report


def import_ohlcv_csv(
    input_path: Path,
    output_dir: Path,
    symbol: str,
    timeframe: str,
    source: str,
    *,
    min_rows: int = 1000,
    max_gap_rate_pct: Optional[float] = None,
) -> tuple[Path, Path, DataQualityReport]:
    """Validate, store, and fingerprint a historical OHLCV CSV."""
    raw = pd.read_csv(input_path)
    data, report = validate_ohlcv_frame(
        raw,
        timeframe,
        min_rows=min_rows,
        max_gap_rate_pct=max_gap_rate_pct,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{symbol.replace('/', '_')}_{timeframe}"
    data_path = output_dir / f"{stem}.csv"
    manifest_path = output_dir / f"{stem}.manifest.json"
    data.to_csv(data_path, index=False, date_format="%Y-%m-%dT%H:%M:%S.%fZ")
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    manifest = {
        "symbol": symbol,
        "source": source,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "sha256": digest,
        "quality": asdict(report),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return data_path, manifest_path, report
