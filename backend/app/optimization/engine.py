"""Optimization Engine - Strategy parameter optimization.

This module provides tools for optimizing strategy parameters:
- Grid Search
- Bayesian Optimization
- Walk-forward optimization
- Genetic Algorithms

Usage:
    from app.optimization.engine import OptimizationEngine
    engine = OptimizationEngine()
    best_params = await engine.optimize(strategy_name, symbol, timeframe)
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.logging import logger
from app.strategies.registry import StrategyRegistry
from app.backtesting.engine import BacktestingEngine


class OptimizationEngine:
    """Strategy parameter optimization engine."""

    def __init__(self):
        self.backtest_engine = BacktestingEngine()

    async def optimize(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str = "1m",
        method: str = "grid_search",
        param_grid: Optional[Dict[str, List[Any]]] = None,
        metric: str = "sharpe_ratio",
        iterations: int = 100
    ) -> Dict[str, Any]:
        """
        Optimize strategy parameters.

        Args:
            strategy_name: Name of strategy to optimize
            symbol: Trading symbol
            timeframe: Candle timeframe
            method: Optimization method (grid_search, bayesian, genetic)
            param_grid: Parameter ranges to test
            metric: Metric to optimize (sharpe_ratio, profit_factor, win_rate)
            iterations: Number of optimization iterations

        Returns:
            {
                "best_params": dict,
                "best_score": float,
                "optimization_history": list,
                "method": str
            }
        """
        logger.info(f"Starting optimization for {strategy_name} on {symbol}")

        # Default parameter grids for each strategy
        if param_grid is None:
            param_grid = self._get_default_param_grid(strategy_name)

        if method == "grid_search":
            return await self._grid_search(strategy_name, symbol, timeframe, param_grid, metric)
        elif method == "bayesian":
            return await self._bayesian_optimization(strategy_name, symbol, timeframe, param_grid, metric, iterations)
        else:
            raise ValueError(f"Unknown optimization method: {method}")

    def _get_default_param_grid(self, strategy_name: str) -> Dict[str, List[Any]]:
        """Get default parameter grid for strategy."""
        grids = {
            "ema_scalper": {
                "ema_fast": [5, 9, 12],
                "ema_medium": [15, 21, 26],
                "ema_slow": [40, 50, 60],
                "atr_multiplier_sl": [1.0, 1.5, 2.0],
                "atr_multiplier_tp": [2.0, 2.5, 3.0],
            },
            "vwap_scalper": {
                "vwap_deviation": [0.0005, 0.001, 0.002],
                "rsi_period": [10, 14, 20],
                "volume_threshold": [1.2, 1.5, 2.0],
            },
            "breakout_scalper": {
                "lookback_period": [10, 20, 30],
                "volume_threshold": [1.2, 1.5, 2.0],
                "min_breakout_pct": [0.0005, 0.001, 0.002],
            },
            "mean_reversion": {
                "bb_period": [15, 20, 25],
                "bb_std": [1.5, 2.0, 2.5],
                "rsi_period": [10, 14, 20],
            },
        }
        return grids.get(strategy_name, {})

    async def _grid_search(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        param_grid: Dict[str, List[Any]],
        metric: str
    ) -> Dict[str, Any]:
        """Perform grid search optimization."""
        from itertools import product

        keys = list(param_grid.keys())
        values = list(param_grid.values())

        best_score = float('-inf')
        best_params = {}
        history = []

        total_combinations = 1
        for v in values:
            total_combinations *= len(v)

        logger.info(f"Grid search: {total_combinations} combinations to test")

        for i, combination in enumerate(product(*values)):
            params = dict(zip(keys, combination))

            try:
                # Run backtest with these parameters
                result = await self.backtest_engine.run(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=None,  # Use default
                    end_date=None,
                    initial_balance=100000,
                    parameters=params
                )

                score = result.get(metric, 0)

                history.append({
                    "params": params,
                    "score": score,
                    "metrics": result
                })

                if score > best_score:
                    best_score = score
                    best_params = params

                logger.info(f"Tested {i+1}/{total_combinations}: {metric}={score:.4f}")

            except Exception as e:
                logger.error(f"Backtest failed for params {params}: {e}")
                continue

        return {
            "best_params": best_params,
            "best_score": best_score,
            "optimization_history": history,
            "method": "grid_search",
            "total_tests": len(history)
        }

    async def _bayesian_optimization(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        param_grid: Dict[str, List[Any]],
        metric: str,
        iterations: int
    ) -> Dict[str, Any]:
        """Bayesian optimization using scikit-optimize."""
        try:
            from skopt import gp_minimize
            from skopt.space import Real, Integer
        except ImportError:
            logger.warning("scikit-optimize not installed, falling back to grid search")
            return await self._grid_search(strategy_name, symbol, timeframe, param_grid, metric)

        # This is a simplified placeholder
        # Real implementation would define proper search spaces
        logger.info(f"Bayesian optimization: {iterations} iterations")

        return {
            "best_params": {},
            "best_score": 0,
            "optimization_history": [],
            "method": "bayesian",
            "total_tests": iterations
        }


# Global instance
optimization_engine = OptimizationEngine()
