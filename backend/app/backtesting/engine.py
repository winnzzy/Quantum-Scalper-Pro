"""Backtesting Engine - Historical strategy testing.

This module provides backtesting capabilities:
- Historical data replay
- Strategy performance evaluation
- Commission and slippage modeling
- Detailed trade logs
- Performance metrics calculation

Usage:
    from app.backtesting.engine import BacktestingEngine
    engine = BacktestingEngine()
    results = await engine.run(strategy_name, symbol, timeframe, start_date, end_date)
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
from pathlib import Path

import pandas as pd
import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.strategies.registry import StrategyRegistry
from app.brokers.paper import PaperBroker, BrokerConfig
from app.brokers.base import OrderSide, OrderType


class BacktestingEngine:
    """Historical backtesting engine."""

    def __init__(self):
        self.data_path = Path(settings.BACKTEST_DATA_PATH)
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.commission = Decimal(str(settings.DEFAULT_COMMISSION))
        self.slippage = Decimal(str(settings.DEFAULT_SLIPPAGE))

    async def run(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str = "1m",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        initial_balance: float = 100000.0,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run backtest.

        Returns:
            {
                "total_trades": int,
                "winning_trades": int,
                "losing_trades": int,
                "win_rate": float,
                "gross_profit": float,
                "gross_loss": float,
                "net_pnl": float,
                "profit_factor": float,
                "sharpe_ratio": float,
                "max_drawdown": float,
                "max_drawdown_pct": float,
                "equity_curve": list,
                "trades": list,
                "parameters": dict
            }
        """
        logger.info(f"Starting backtest: {strategy_name} on {symbol} {timeframe}")

        # Load historical data
        df = await self._load_data(symbol, timeframe, start_date, end_date)

        if df is None or len(df) < 50:
            return {"error": "Insufficient historical data"}

        # Initialize strategy and paper broker
        strategy = StrategyRegistry.get_strategy(strategy_name, parameters)
        broker = PaperBroker(BrokerConfig())
        broker.set_balance(Decimal(str(initial_balance)))
        await broker.connect()

        # Run backtest
        trades = []
        equity_curve = [initial_balance]
        peak_equity = initial_balance
        max_drawdown = 0.0
        max_drawdown_pct = 0.0

        # Process each candle
        for i in range(50, len(df)):
            window = df.iloc[:i+1]

            # Get signal
            result = await strategy.analyze(symbol, window)

            if result and result.signal.type.value in ["buy", "sell"]:
                signal = result.signal
                current_price = float(signal.price)

                # Check if we have an open position
                positions = await broker.get_positions(symbol)

                if not positions:
                    # Open new position
                    if signal.type.value == "buy":
                        side = OrderSide.BUY
                    else:
                        side = OrderSide.SELL

                    # Calculate position size (1% risk)
                    balance = float(broker._balance)
                    risk_amount = balance * 0.01

                    if signal.stop_loss:
                        sl_distance = abs(current_price - float(signal.stop_loss))
                        if sl_distance > 0:
                            quantity = risk_amount / sl_distance
                        else:
                            quantity = 0.01
                    else:
                        quantity = 0.01

                    await broker.place_order(
                        symbol=symbol,
                        side=side,
                        order_type=OrderType.MARKET,
                        quantity=Decimal(str(quantity)),
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit
                    )

                elif positions:
                    # Check if signal is opposite direction - close position
                    pos = positions[0]
                    if (signal.type.value == "buy" and pos.side == OrderSide.SELL) or                        (signal.type.value == "sell" and pos.side == OrderSide.BUY):
                        close_result = await broker.close_position(symbol)
                        if close_result.success:
                            pnl = float(close_result.filled_price or 0) - float(pos.entry_price)
                            if pos.side == OrderSide.SELL:
                                pnl = -pnl
                            trades.append({
                                "entry_price": float(pos.entry_price),
                                "exit_price": float(close_result.filled_price or 0),
                                "pnl": pnl * float(pos.quantity),
                                "side": pos.side.value,
                                "quantity": float(pos.quantity)
                            })

            # Update equity curve
            account = await broker.get_account_info()
            current_equity = float(account.equity)
            equity_curve.append(current_equity)

            # Calculate drawdown
            if current_equity > peak_equity:
                peak_equity = current_equity

            dd = peak_equity - current_equity
            if dd > max_drawdown:
                max_drawdown = dd
                max_drawdown_pct = (dd / peak_equity) * 100 if peak_equity > 0 else 0

        # Close any remaining positions
        positions = await broker.get_positions()
        for pos in positions:
            await broker.close_position(pos.symbol)

        await broker.disconnect()

        # Calculate metrics
        winning_trades = [t for t in trades if t["pnl"] > 0]
        losing_trades = [t for t in trades if t["pnl"] <= 0]

        gross_profit = sum(t["pnl"] for t in winning_trades)
        gross_loss = abs(sum(t["pnl"] for t in losing_trades))
        net_pnl = gross_profit - gross_loss

        total_trades = len(trades)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Sharpe ratio (simplified)
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] > 0:
                ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                returns.append(ret)

        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24 * 60)  # Annualized for 1m
        else:
            sharpe = 0

        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "net_pnl": round(net_pnl, 2),
            "profit_factor": round(profit_factor, 4),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "equity_curve": equity_curve,
            "trades": trades,
            "parameters": parameters or {},
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": strategy_name
        }

    async def _load_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> Optional[pd.DataFrame]:
        """Load historical OHLCV data."""
        # Try to load from file first
        file_path = self.data_path / f"{symbol.replace('/', '_')}_{timeframe}.csv"

        if file_path.exists():
            df = pd.read_csv(file_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            if start_date:
                df = df[df['timestamp'] >= start_date]
            if end_date:
                df = df[df['timestamp'] <= end_date]

            return df

        # Generate synthetic data for testing
        logger.warning(f"No historical data found for {symbol}, generating synthetic data")
        return self._generate_synthetic_data(symbol, timeframe)

    def _generate_synthetic_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Generate synthetic OHLCV data for testing."""
        np.random.seed(42)

        # Generate 1000 candles
        n = 1000
        base_price = 50000 if "BTC" in symbol else 3500 if "ETH" in symbol else 1.0

        timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=n, freq='1min')

        prices = [base_price]
        for i in range(1, n):
            change = np.random.normal(0, 0.001)  # 0.1% volatility
            prices.append(prices[-1] * (1 + change))

        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': prices,
            'high': [p * (1 + abs(np.random.normal(0, 0.0005))) for p in prices],
            'low': [p * (1 - abs(np.random.normal(0, 0.0005))) for p in prices],
            'close': [p * (1 + np.random.normal(0, 0.0003)) for p in prices],
            'volume': np.random.randint(1000, 100000, n)
        })

        return df


# Global instance
backtest_engine = BacktestingEngine()
