"""Verified Binance public kline download and normalization."""
from __future__ import annotations

import hashlib
import io
import tempfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.backtesting.data import DataQualityReport, import_ohlcv_csv


BASE_URL = "https://data.binance.vision"
BINANCE_KLINE_COLUMNS = (
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trade_count", "taker_buy_base_volume",
    "taker_buy_quote_volume", "ignore",
)


def _month_range(start: date, end: date) -> Iterable[tuple[int, int]]:
    if start > end:
        raise ValueError("start month must not be after end month")
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month == 13:
            year += 1
            month = 1


def _monthly_archive_url(
    market: str, symbol: str, timeframe: str, year: int, month: int
) -> str:
    if market not in {"spot", "um", "cm"}:
        raise ValueError("market must be one of: spot, um, cm")
    root = "spot" if market == "spot" else f"futures/{market}"
    filename = f"{symbol.upper()}-{timeframe}-{year}-{month:02d}.zip"
    return (
        f"{BASE_URL}/data/{root}/monthly/klines/"
        f"{symbol.upper()}/{timeframe}/{filename}"
    )


def _verify_checksum(payload: bytes, checksum_text: str, filename: str) -> None:
    fields = checksum_text.strip().split()
    if not fields:
        raise ValueError(f"Empty checksum for {filename}")
    expected = fields[0].lower()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(
            f"Checksum mismatch for {filename}: expected {expected}, got {actual}"
        )


def _parse_binance_kline_zip(payload: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError("Binance archive must contain exactly one CSV file")
        with archive.open(csv_names[0]) as stream:
            frame = pd.read_csv(stream, header=None, names=BINANCE_KLINE_COLUMNS)

    if frame.empty:
        raise ValueError("Binance archive contains no candles")
    numeric_timestamp = pd.to_numeric(frame["open_time"], errors="raise")
    # Binance Spot changed archived timestamps from milliseconds to
    # microseconds on 2025-01-01. Magnitude detection safely supports both.
    units = numeric_timestamp.map(lambda value: "us" if value >= 10**15 else "ms")
    timestamps = pd.Series(index=frame.index, dtype="datetime64[ns, UTC]")
    for unit in ("ms", "us"):
        mask = units == unit
        if mask.any():
            timestamps.loc[mask] = pd.to_datetime(
                numeric_timestamp.loc[mask], unit=unit, utc=True
            )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": frame["open"],
            "high": frame["high"],
            "low": frame["low"],
            "close": frame["close"],
            "volume": frame["volume"],
        }
    )


def download_binance_monthly_klines(
    *,
    archive_symbol: str,
    storage_symbol: str,
    timeframe: str,
    start_month: date,
    end_month: date,
    output_dir: Path,
    market: str = "spot",
    min_rows: int = 1000,
    max_gap_rate_pct: float | None = None,
    timeout_seconds: int = 60,
) -> tuple[Path, Path, DataQualityReport]:
    """Download checksum-verified Binance archives and import canonical OHLCV."""
    frames: list[pd.DataFrame] = []
    source_urls: list[str] = []
    for year, month in _month_range(start_month, end_month):
        url = _monthly_archive_url(
            market, archive_symbol, timeframe, year, month
        )
        filename = url.rsplit("/", 1)[-1]
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            payload = response.read()
        with urllib.request.urlopen(
            f"{url}.CHECKSUM", timeout=timeout_seconds
        ) as response:
            checksum = response.read().decode("utf-8")
        _verify_checksum(payload, checksum, filename)
        frames.append(_parse_binance_kline_zip(payload))
        source_urls.append(url)

    combined = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    source = (
        f"Binance public data ({market}); {source_urls[0]} through "
        f"{source_urls[-1]}; checksums verified"
    )
    with tempfile.TemporaryDirectory(prefix="qsp-binance-") as temp_dir:
        raw_path = Path(temp_dir) / "combined.csv"
        combined.to_csv(raw_path, index=False)
        return import_ohlcv_csv(
            raw_path,
            output_dir,
            storage_symbol,
            timeframe,
            source,
            min_rows=min_rows,
            max_gap_rate_pct=max_gap_rate_pct,
        )
