# Binance Public Data Integration

Quantum Scalper Pro can download monthly Spot, USD-M, or COIN-M kline archives
from Binance's official public dataset. Every archive is verified against its
companion SHA-256 checksum before any candle is imported.

From `backend/`, download a bounded period:

```bash
python -m scripts.download_binance_data \
  --archive-symbol BTCUSDT \
  --storage-symbol BTC/USDT \
  --timeframe 1m \
  --start 2025-01 \
  --end 2025-12 \
  --market spot \
  --max-gap-rate-pct 1
```

The downloader supports Binance's millisecond archives and the microsecond Spot
timestamps used from January 2025 onward. The result is passed through the same
strict chronological/OHLCV validator as manually imported data, then stored with
a provenance manifest under `BACKTEST_DATA_PATH`.

Downloaded datasets are intentionally excluded from Git. Keep the newest
chronological segment untouched as a final holdout until strategy selection and
parameter tuning are complete.
