"""Binance archive normalization and integrity tests."""
import hashlib
import io
import zipfile
from datetime import date

import pytest

from app.backtesting.binance_data import (
    _month_range,
    _monthly_archive_url,
    _parse_binance_kline_zip,
    _verify_checksum,
)


def kline_zip(timestamp: int) -> bytes:
    row = (
        f"{timestamp},100,101,99,100.5,12,0,0,1,0,0,0\n"
    ).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BTCUSDT-1m.csv", row)
    return buffer.getvalue()


def test_month_range_crosses_year_boundary():
    assert list(_month_range(date(2025, 11, 1), date(2026, 2, 1))) == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2)
    ]


def test_official_archive_path_for_spot_and_futures():
    spot = _monthly_archive_url("spot", "btcusdt", "1m", 2026, 1)
    futures = _monthly_archive_url("um", "btcusdt", "1m", 2026, 1)
    assert "/data/spot/monthly/klines/BTCUSDT/1m/" in spot
    assert "/data/futures/um/monthly/klines/BTCUSDT/1m/" in futures


def test_checksum_verification_rejects_modified_archive():
    payload = b"verified archive"
    checksum = f"{hashlib.sha256(payload).hexdigest()}  archive.zip"
    _verify_checksum(payload, checksum, "archive.zip")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        _verify_checksum(payload + b"changed", checksum, "archive.zip")


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (1735689600000, "2025-01-01T00:00:00+00:00"),
        (1735689600000000, "2025-01-01T00:00:00+00:00"),
    ],
)
def test_parser_supports_millisecond_and_microsecond_timestamps(
    timestamp: int, expected: str
):
    parsed = _parse_binance_kline_zip(kline_zip(timestamp))
    assert parsed.loc[0, "timestamp"].isoformat() == expected
    assert parsed.loc[0, "close"] == 100.5
