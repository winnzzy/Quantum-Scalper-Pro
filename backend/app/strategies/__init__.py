"""Trading strategies for Quantum Scalper Pro."""
from app.strategies.base import BaseStrategy, Signal, SignalType, StrategyResult
from app.strategies.ema_scalper import EMAScalper
from app.strategies.vwap_scalper import VWAPScalper
from app.strategies.breakout_scalper import BreakoutScalper
from app.strategies.mean_reversion import MeanReversionScalper
from app.strategies.registry import StrategyRegistry

__all__ = [
    "BaseStrategy", "Signal", "SignalType", "StrategyResult",
    "EMAScalper", "VWAPScalper", "BreakoutScalper", "MeanReversionScalper",
    "StrategyRegistry",
]
