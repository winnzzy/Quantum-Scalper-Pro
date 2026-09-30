# BTC and Gold Focus

Quantum Scalper Pro supports exactly two canonical markets:

| Market | Canonical symbol | Live adapter | Historical evidence |
|---|---|---|---|
| Bitcoin | `BTC/USDT` | Binance testnet/futures or paper | Binance public spot/USD-M archives |
| Spot gold / broker CFD | `XAU/USD` | MT5 or paper | Export from the intended MT5 broker |

Aliases such as `BTCUSD`, `BTCUSDT`, `XAUUSD`, and `GOLD` normalize to the
canonical symbols at API and import boundaries. Unsupported instruments are
rejected before a strategy or broker is invoked. Binance is never offered for
gold and MT5 is never offered for Bitcoin in this focused build.

## Strategy thesis

`dual_market_regime` is the default candidate. It does not share one parameter
set across both markets. Each profile requires:

1. aligned 20/50/200 EMAs;
2. minimum ADX trend strength;
3. an asset-specific RSI band;
4. an ATR floor and ceiling to avoid dead or disorderly regimes;
5. a pullback reclaim or prior-range breakout; and
6. asset-specific stop distance and reward/risk.

Bitcoin additionally requires volume confirmation. Gold does not require it
because MT5 commonly supplies broker tick volume, not consolidated market
volume. Both profiles cap configured risk at 0.50% per trade and default to
0.25%.

These are hypotheses, not optimized claims. Promote a parameter set only after
rolling out-of-sample validation, an untouched holdout, paper trading, and
venue-specific cost calibration. Reject it if profitability depends on a
single period, a small trade count, unrealistic fills, or omitted financing.

## Personal deployment gate

- Use separate strategy configurations and evidence for BTC and gold.
- Keep Binance testnet and MT5 demo enabled until order size, stop placement,
  reconnection, and reconciliation have passed end-to-end checks.
- Record the exact MT5 gold symbol in `MT5_XAU_SYMBOL`.
- Never substitute PAXG data for broker XAU/USD evidence.
- Start at 0.25% risk or less; do not raise risk to compensate for weak edge.
- Pause after the configured daily loss, drawdown, or consecutive-loss limit.
- Compare live slippage and spread with validation assumptions every week.

No strategy can always win or print money. The system is designed to make
unsupported markets impossible, losses bounded, assumptions explicit, and an
edge falsifiable before meaningful capital is exposed.

## Qualification command

After importing the venue-matched 5-minute dataset, run the controlled preset:

```bash
cd backend
python -m scripts.qualify_market --symbol BTC/USDT
python -m scripts.qualify_market --symbol XAU/USD
```

The process reserves the last 6,000 candles as an untouched holdout. Earlier
candles are used for rolling parameter selection and unseen test windows. The
most consistently selected candidate is then run once on the holdout and once
more with 1.5× spread, 1.5× commission, and 2× slippage.

An approval requires all promotion checks to pass. The resulting qualification
file contains the dataset SHA-256. Changing or replacing the CSV invalidates
the approval automatically. Binance and MT5 live starts fail closed when the
dataset, provenance manifest, qualification report, or approval is missing.
