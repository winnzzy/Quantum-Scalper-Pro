"""Strategy registry for managing and instantiating strategies."""
from typing import Dict, Type, Optional, Any

from app.strategies.base import BaseStrategy
from app.strategies.ema_scalper import EMAScalper
from app.strategies.vwap_scalper import VWAPScalper
from app.strategies.breakout_scalper import BreakoutScalper
from app.strategies.mean_reversion import MeanReversionScalper


class StrategyRegistry:
    """Registry for strategy management."""

    _strategies: Dict[str, Type[BaseStrategy]] = {
        "ema_scalper": EMAScalper,
        "vwap_scalper": VWAPScalper,
        "breakout_scalper": BreakoutScalper,
        "mean_reversion": MeanReversionScalper,
    }

    @classmethod
    def register(cls, name: str, strategy_class: Type[BaseStrategy]):
        """Register a new strategy."""
        cls._strategies[name] = strategy_class

    @classmethod
    def get_strategy(cls, name: str, config: Optional[Dict[str, Any]] = None) -> BaseStrategy:
        """Get strategy instance by name."""
        if name not in cls._strategies:
            raise ValueError(f"Strategy '{name}' not found. Available: {list(cls._strategies.keys())}")
        return cls._strategies[name](config)

    @classmethod
    def list_strategies(cls) -> list:
        """List all available strategies."""
        return list(cls._strategies.keys())

    @classmethod
    def get_strategy_info(cls, name: str) -> Dict[str, Any]:
        """Get strategy information."""
        if name not in cls._strategies:
            raise ValueError(f"Strategy '{name}' not found")

        strategy_class = cls._strategies[name]
        instance = strategy_class()

        return {
            "name": instance.name,
            "class": strategy_class.__name__,
            "indicators": instance.get_required_indicators(),
            "default_config": instance.config,
        }
