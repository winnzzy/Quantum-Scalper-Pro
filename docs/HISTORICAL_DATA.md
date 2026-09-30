# Historical Data for Strategy Validation

Backtests do not treat generated candles as performance evidence. Import a
timestamped vendor or exchange CSV before running walk-forward validation:

```bash
cd backend
python -m scripts.import_market_data \
  --input /path/to/BTCUSDT-1m.csv \
  --symbol BTC/USDT \
  --timeframe 1m \
  --source "exchange export 2024-2026" \
  --max-gap-rate-pct 1
```

The CSV must contain `timestamp,open,high,low,close,volume`. The importer rejects
duplicate timestamps, non-chronological data, invalid prices, negative volume,
and broken OHLC relationships. It writes the canonical dataset under
`BACKTEST_DATA_PATH` together with a provenance manifest containing its source,
quality statistics, and SHA-256 fingerprint.

Review reported gaps before using results for strategy decisions. Session
closures can create legitimate gaps in some markets, so choose a gap threshold
appropriate to the source and instrument. Keep a final chronological period
untouched until parameter selection is complete.

This focused build accepts only `BTC/USDT` and `XAU/USD`. For Bitcoin, use the
checksum-verified Binance downloader documented in `BINANCE_PUBLIC_DATA.md`.
For gold, export candles from the same MT5 broker and symbol you intend to
trade; gold CFD prices, sessions, tick volume, spreads, and suffixes vary by
broker. Convert the export to the canonical columns above, then import it as:

```bash
cd backend
python -m scripts.import_market_data \
  --input /path/to/your-broker-XAUUSD-5m.csv \
  --symbol XAU/USD \
  --timeframe 5m \
  --source "Broker name, server, exact symbol, export date" \
  --max-gap-rate-pct 20
```

Do not compare a PAXG crypto backtest with execution on spot-gold/CFD. They are
different instruments. Backtest costs default to market-specific estimates in
the API, but final validation must override them with observed spreads,
commission, slippage, and financing from the actual account.
