"""Canonical market definitions for the focused BTC and gold product."""
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class MarketProfile:
    symbol: str
    name: str
    asset_class: str
    data_source: str
    allowed_brokers: tuple[str, ...]
    allowed_timeframes: tuple[str, ...]
    default_timeframe: str
    default_risk_percent: float
    max_risk_percent: float
    backtest_spread_pct: float
    backtest_commission_rate: float
    backtest_slippage_rate: float
    max_live_spread_pct: float


MARKETS: Mapping[str, MarketProfile] = {
    "BTC/USDT": MarketProfile(
        symbol="BTC/USDT",
        name="Bitcoin / Tether",
        asset_class="crypto",
        data_source="Binance public spot or USD-M archives",
        allowed_brokers=("paper", "binance_testnet", "binance_futures"),
        allowed_timeframes=("1m", "5m", "15m", "30m", "1h", "4h", "1d"),
        default_timeframe="5m",
        default_risk_percent=0.25,
        max_risk_percent=0.50,
        backtest_spread_pct=0.00020,
        backtest_commission_rate=0.00040,
        backtest_slippage_rate=0.00010,
        max_live_spread_pct=0.0010,
    ),
    "XAU/USD": MarketProfile(
        symbol="XAU/USD",
        name="Spot Gold / US Dollar",
        asset_class="metal_cfd",
        data_source="The execution broker's MT5 candle export",
        allowed_brokers=("paper", "mt5"),
        allowed_timeframes=("1m", "5m", "15m", "30m", "1h", "4h", "1d"),
        default_timeframe="5m",
        default_risk_percent=0.25,
        max_risk_percent=0.50,
        backtest_spread_pct=0.00015,
        backtest_commission_rate=0.00000,
        backtest_slippage_rate=0.00010,
        max_live_spread_pct=0.0015,
    ),
}

_ALIASES = {
    "BTCUSD": "BTC/USDT",
    "BTCUSDT": "BTC/USDT",
    "BTC-USDT": "BTC/USDT",
    "BTC_USDT": "BTC/USDT",
    "BTC/USDT": "BTC/USDT",
    "GOLD": "XAU/USD",
    "XAUUSD": "XAU/USD",
    "XAU-USD": "XAU/USD",
    "XAU_USD": "XAU/USD",
    "XAU/USD": "XAU/USD",
}


def normalize_symbol(value: str) -> str:
    """Return a canonical supported symbol or raise a precise error."""
    key = value.strip().upper()
    try:
        return _ALIASES[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported market '{value}'. Only BTC/USDT and XAU/USD are supported."
        ) from exc


def get_market(value: str) -> MarketProfile:
    return MARKETS[normalize_symbol(value)]


def validate_market_broker(symbol: str, broker_type: str) -> None:
    profile = get_market(symbol)
    if broker_type not in profile.allowed_brokers:
        allowed = ", ".join(profile.allowed_brokers)
        raise ValueError(
            f"{profile.symbol} cannot use broker '{broker_type}'. Allowed: {allowed}."
        )


def validate_timeframe(symbol: str, timeframe: str) -> None:
    profile = get_market(symbol)
    if timeframe not in profile.allowed_timeframes:
        raise ValueError(f"Timeframe '{timeframe}' is not supported for {profile.symbol}.")


def public_market_catalog() -> list[dict]:
    return [
        {
            "symbol": profile.symbol,
            "name": profile.name,
            "asset_class": profile.asset_class,
            "data_source": profile.data_source,
            "allowed_brokers": list(profile.allowed_brokers),
            "allowed_timeframes": list(profile.allowed_timeframes),
            "default_timeframe": profile.default_timeframe,
            "default_risk_percent": profile.default_risk_percent,
            "max_risk_percent": profile.max_risk_percent,
        }
        for profile in MARKETS.values()
    ]
