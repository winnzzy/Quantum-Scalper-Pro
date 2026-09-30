"""Run the controlled research preset and write dataset-bound evidence."""
import argparse
import asyncio
import json

from app.backtesting.engine import backtest_engine
from app.backtesting.evidence import save_qualification
from app.backtesting.presets import get_validation_preset
from app.core.markets import get_market, normalize_symbol


async def qualify(symbol: str) -> int:
    symbol = normalize_symbol(symbol)
    preset = get_validation_preset(symbol)
    market = get_market(symbol)
    result = await backtest_engine.run_walk_forward(
        symbol=symbol,
        risk_per_trade_pct=market.default_risk_percent,
        spread_pct=market.backtest_spread_pct,
        commission_rate=market.backtest_commission_rate,
        slippage_rate=market.backtest_slippage_rate,
        **preset,
    )
    if "error" in result:
        print(json.dumps(result, indent=2))
        return 1
    evidence_path = save_qualification(symbol, preset["timeframe"], result)
    print(json.dumps({
        "symbol": symbol,
        "promotion_gate": result["promotion_gate"],
        "out_of_sample_summary": result["out_of_sample_summary"],
        "untouched_holdout": result["untouched_holdout"],
        "adverse_cost_holdout": result["adverse_cost_holdout"],
        "evidence_path": str(evidence_path),
    }, indent=2))
    return 0 if result["promotion_gate"]["approved"] else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Qualify BTC/USDT or XAU/USD")
    parser.add_argument("--symbol", required=True, choices=["BTC/USDT", "XAU/USD"])
    args = parser.parse_args()
    raise SystemExit(asyncio.run(qualify(args.symbol)))


if __name__ == "__main__":
    main()
