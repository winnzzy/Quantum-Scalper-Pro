"""Import a vendor/exported OHLCV CSV into the backtesting data directory."""
import argparse
from pathlib import Path

from app.backtesting.data import import_ohlcv_csv
from app.core.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and import chronological OHLCV market data"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(settings.BACKTEST_DATA_PATH)
    )
    parser.add_argument("--min-rows", type=int, default=1000)
    parser.add_argument("--max-gap-rate-pct", type=float)
    args = parser.parse_args()

    data_path, manifest_path, report = import_ohlcv_csv(
        args.input,
        args.output_dir,
        args.symbol,
        args.timeframe,
        args.source,
        min_rows=args.min_rows,
        max_gap_rate_pct=args.max_gap_rate_pct,
    )
    print(f"Imported {report.rows} candles to {data_path}")
    print(f"Gap rate: {report.gap_rate_pct}% ({report.missing_intervals} intervals)")
    print(f"Provenance manifest: {manifest_path}")


if __name__ == "__main__":
    main()
