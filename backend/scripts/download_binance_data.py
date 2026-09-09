"""Download and import checksum-verified Binance monthly kline archives."""
import argparse
from datetime import date
from pathlib import Path

from app.backtesting.binance_data import download_binance_monthly_klines
from app.core.config import settings


def month(value: str) -> date:
    try:
        return date.fromisoformat(f"{value}-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download verified Binance public monthly klines"
    )
    parser.add_argument("--archive-symbol", required=True, help="e.g. BTCUSDT")
    parser.add_argument("--storage-symbol", required=True, help="e.g. BTC/USDT")
    parser.add_argument("--timeframe", required=True, help="e.g. 1m")
    parser.add_argument("--start", required=True, type=month, help="YYYY-MM")
    parser.add_argument("--end", required=True, type=month, help="YYYY-MM")
    parser.add_argument("--market", choices=("spot", "um", "cm"), default="spot")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(settings.BACKTEST_DATA_PATH)
    )
    parser.add_argument("--min-rows", type=int, default=1000)
    parser.add_argument("--max-gap-rate-pct", type=float)
    args = parser.parse_args()

    data_path, manifest_path, report = download_binance_monthly_klines(
        archive_symbol=args.archive_symbol,
        storage_symbol=args.storage_symbol,
        timeframe=args.timeframe,
        start_month=args.start,
        end_month=args.end,
        output_dir=args.output_dir,
        market=args.market,
        min_rows=args.min_rows,
        max_gap_rate_pct=args.max_gap_rate_pct,
    )
    print(f"Imported {report.rows} verified candles to {data_path}")
    print(f"Gap rate: {report.gap_rate_pct}% ({report.missing_intervals} intervals)")
    print(f"Provenance manifest: {manifest_path}")


if __name__ == "__main__":
    main()
