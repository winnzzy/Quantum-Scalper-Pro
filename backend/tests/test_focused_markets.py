"""Regression tests for the BTC/gold product boundary."""
import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.api import api_router
from app.api.v1.backtesting import WalkForwardRequest
from app.api.v1.trading import StrategyConfigCreate, TradeCreate
from app.core.markets import get_market, normalize_symbol, validate_market_broker
from app.strategies.dual_market_regime import DualMarketRegimeStrategy
from app.strategies.registry import StrategyRegistry
from app.risk.engine import RiskManagementEngine


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("BTCUSD", "BTC/USDT"), ("btcusdt", "BTC/USDT"), ("GOLD", "XAU/USD"), ("xauusd", "XAU/USD")],
)
def test_market_aliases_are_canonical(alias, canonical):
    assert normalize_symbol(alias) == canonical


def test_unsupported_market_is_rejected_everywhere():
    with pytest.raises(ValueError, match="Only BTC/USDT and XAU/USD"):
        normalize_symbol("ETH/USDT")
    with pytest.raises(ValidationError):
        WalkForwardRequest(strategy_name="ema_scalper", symbol="EUR/USD")
    with pytest.raises(ValidationError):
        StrategyConfigCreate(name="bad", strategy_type="ema_scalper", symbols=["PAXG/USDT"])


def test_broker_market_compatibility_is_enforced():
    validate_market_broker("BTC/USDT", "binance_testnet")
    validate_market_broker("XAU/USD", "mt5")
    with pytest.raises(ValueError, match="cannot use broker 'mt5'"):
        validate_market_broker("BTC/USDT", "mt5")
    with pytest.raises(ValidationError):
        TradeCreate(symbol="XAUUSD", direction="buy", quantity=0.01, broker_type="binance_futures")


def test_risk_is_capped_and_defaults_are_conservative():
    config = StrategyConfigCreate(name="gold", strategy_type="dual_market_regime", symbols=["GOLD"])
    assert config.symbols == ["XAU/USD"]
    assert config.risk_per_trade == get_market("XAU/USD").default_risk_percent == 0.25
    with pytest.raises(ValidationError):
        StrategyConfigCreate(
            name="too much", strategy_type="dual_market_regime",
            symbols=["BTC/USDT"], risk_per_trade=0.51,
        )


def test_focused_strategy_and_path_routes_are_registered():
    assert StrategyRegistry.get_strategy("dual_market_regime").name == "Dual_Market_Regime"
    assert set(DualMarketRegimeStrategy.PROFILES) == {"BTC/USDT", "XAU/USD"}
    paths = {route.path for route in api_router.routes}
    assert "/api/v1/trading/markets" in paths
    assert "/api/v1/trading/market/{symbol:path}" in paths


def test_weekend_gate_distinguishes_always_open_crypto_from_gold():
    engine = RiskManagementEngine(db=MagicMock())
    profile = MagicMock(weekend_protection_enabled=True)
    saturday = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    assert engine._check_weekend_protection(profile, "BTC/USDT", saturday)["allowed"]
    gold = engine._check_weekend_protection(profile, "XAU/USD", saturday)
    assert not gold["allowed"]
