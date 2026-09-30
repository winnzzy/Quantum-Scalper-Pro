"""Bounded research spaces for the focused BTC and gold strategy."""
from copy import deepcopy

from app.core.markets import normalize_symbol


_PRESETS = {
    "BTC/USDT": {
        "strategy_name": "dual_market_regime", "timeframe": "5m",
        "initial_balance": 100000.0,
        "train_candles": 12000, "test_candles": 3000,
        "step_candles": 3000, "holdout_candles": 6000,
        "min_train_trades": 12,
        "parameter_candidates": [
            {"min_adx": 20.0, "stop_atr": 1.6, "reward_risk": 2.0, "min_volume_ratio": 1.05},
            {"min_adx": 22.0, "stop_atr": 1.8, "reward_risk": 2.2, "min_volume_ratio": 1.10},
            {"min_adx": 25.0, "stop_atr": 2.0, "reward_risk": 2.4, "min_volume_ratio": 1.15},
        ],
    },
    "XAU/USD": {
        "strategy_name": "dual_market_regime", "timeframe": "5m",
        "initial_balance": 100000.0,
        "train_candles": 12000, "test_candles": 3000,
        "step_candles": 3000, "holdout_candles": 6000,
        "min_train_trades": 12,
        "parameter_candidates": [
            {"min_adx": 18.0, "stop_atr": 1.4, "reward_risk": 1.8, "breakout_lookback": 20},
            {"min_adx": 20.0, "stop_atr": 1.6, "reward_risk": 2.0, "breakout_lookback": 24},
            {"min_adx": 23.0, "stop_atr": 1.8, "reward_risk": 2.2, "breakout_lookback": 30},
        ],
    },
}


def get_validation_preset(symbol: str) -> dict:
    """Return an isolated copy so callers cannot mutate global research policy."""
    return deepcopy(_PRESETS[normalize_symbol(symbol)])
