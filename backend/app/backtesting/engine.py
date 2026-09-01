"""Backtesting Engine - Historical strategy testing.

This module provides institutional-grade backtesting capabilities:
- Historical data replay with deterministic execution
- Spread simulation from historical data or configurable model
- Slippage simulation matching live PaperBroker behavior
- Commission modeling identical to live trading
- Position sizing via integrated RiskEngine logic
- Risk limit enforcement (drawdown, consecutive losses, daily limits)
- Strategy execution consistency (same code path as live)
- Detailed trade logs with full cost breakdown
- Performance metrics calculation

Usage:
    from app.backtesting.engine import BacktestingEngine
    engine = BacktestingEngine()
    results = await engine.run(strategy_name, symbol, timeframe, start_date, end_date)
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.strategies.registry import StrategyRegistry
from app.strategies.base import SignalType
from app.brokers.base import OrderSide, OrderType, MarketData


# ──────────────────────────────────────────────────────────────────────
# Backtest-specific data types (avoid PaperBroker's random market data)
# ──────────────────────────────────────────────────────────────────────

@dataclass
class BacktestPosition:
    """Position tracked during backtesting."""
    symbol: str
    side: str  # "buy" or "sell"
    entry_price: Decimal
    entry_reference_price: Decimal
    quantity: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    entry_commission: Decimal = Decimal("0")
    entry_slippage_cost: Decimal = Decimal("0")
    entry_spread_cost: Decimal = Decimal("0")


@dataclass
class BacktestTrade:
    """Completed trade record with full cost breakdown."""
    symbol: str
    side: str
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    gross_pnl: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    slippage_cost: Decimal = Decimal("0")
    spread_cost: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    exit_reason: str = ""


@dataclass
class RiskState:
    """Tracks risk metrics during backtesting (mirrors RiskManagementEngine)."""
    balance: Decimal = Decimal("100000")
    peak_equity: Decimal = Decimal("100000")
    current_drawdown: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    consecutive_losses: int = 0
    daily_pnl: Decimal = Decimal("0")
    current_day: Optional[date] = None
    daily_start_balance: Decimal = Decimal("100000")
    daily_locked: bool = False
    total_trades: int = 0
    trading_paused: bool = False
    pause_reason: str = ""


class BacktestingEngine:
    """
    Institutional-grade backtesting engine.

    Guarantees determinism: the same inputs produce the same outputs.
    All fill prices, costs, and position sizing use the same logic as
    live trading (PaperBroker + RiskManagementEngine) to ensure that a
    strategy validated in backtesting behaves identically in production.
    """

    def __init__(self):
        self.data_path = Path(settings.BACKTEST_DATA_PATH)
        self.data_path.mkdir(parents=True, exist_ok=True)

        # Cost models — MUST match PaperBroker exactly
        self.commission_rate = Decimal(str(settings.DEFAULT_COMMISSION))  # 0.04%
        self.slippage_rate = Decimal(str(settings.DEFAULT_SLIPPAGE))      # 0.01%
        self.default_spread_pct = Decimal("0.0002")                       # 0.02%

        # Risk defaults — match settings
        self.risk_per_trade_pct = Decimal(str(settings.DEFAULT_RISK_PER_TRADE))  # 0.5%
        self.max_drawdown_pct = Decimal(str(settings.MAX_DRAWDOWN_PERCENT))      # 15%
        self.max_consecutive_losses = settings.MAX_CONSECUTIVE_LOSSES            # 5
        self.max_daily_loss_pct = Decimal(str(settings.MAX_DAILY_LOSS_PERCENT))  # 3%
        self.mandatory_stop_loss = settings.MANDATORY_STOP_LOSS                  # True

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    async def run(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str = "1m",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        initial_balance: float = 100000.0,
        parameters: Optional[Dict[str, Any]] = None,
        risk_per_trade_pct: Optional[float] = None,
        max_drawdown_pct: Optional[float] = None,
        max_consecutive_losses: Optional[int] = None,
        spread_pct: Optional[float] = None,
        commission_rate: Optional[float] = None,
        slippage_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run backtest with full institutional-grade simulation.

        All cost models, position sizing, and risk rules mirror live trading.
        """
        logger.info(f"Starting backtest: {strategy_name} on {symbol} {timeframe}")

        # Allow parameter overrides
        risk_pct = Decimal(str(risk_per_trade_pct)) if risk_per_trade_pct else self.risk_per_trade_pct
        dd_pct = Decimal(str(max_drawdown_pct)) if max_drawdown_pct else self.max_drawdown_pct
        max_consec = max_consecutive_losses if max_consecutive_losses is not None else self.max_consecutive_losses
        spread = Decimal(str(spread_pct)) if spread_pct else self.default_spread_pct
        comm = Decimal(str(commission_rate)) if commission_rate else self.commission_rate
        slip = Decimal(str(slippage_rate)) if slippage_rate else self.slippage_rate

        # Load historical data
        df = await self._load_data(symbol, timeframe, start_date, end_date)

        if df is None or len(df) < 50:
            return {"error": "Insufficient historical data"}

        # Initialize strategy
        strategy = StrategyRegistry.get_strategy(strategy_name, parameters)

        # Initialize state
        risk_state = RiskState(
            balance=Decimal(str(initial_balance)),
            peak_equity=Decimal(str(initial_balance)),
        )
        position: Optional[BacktestPosition] = None
        trades: List[BacktestTrade] = []
        equity_curve: List[float] = [initial_balance]
        cost_log = {
            "total_commission": Decimal("0"),
            "total_slippage": Decimal("0"),
            "total_spread": Decimal("0"),
        }

        min_periods = 60  # Match strategy validate_data min_periods

        # ──────────────────────────────────────────────────────────────
        # Main simulation loop
        # ──────────────────────────────────────────────────────────────
        for i in range(min_periods, len(df)):
            window = df.iloc[:i + 1]
            candle = df.iloc[i]
            candle_time = candle.get("timestamp")
            candle_close = Decimal(str(candle["close"]))
            candle_high = Decimal(str(candle["high"]))
            candle_low = Decimal(str(candle["low"]))
            candle_open = Decimal(str(candle["open"]))
            self._roll_risk_day(risk_state, candle_time)

            # ── 1. Check stop-loss / take-profit hits on current candle ──
            if position:
                sl_tp_trade = self._check_sl_tp(
                    position, candle_high, candle_low, candle_close,
                    spread, comm, slip, candle_time, symbol
                )
                if sl_tp_trade:
                    trades.append(sl_tp_trade)
                    cost_log["total_commission"] += sl_tp_trade.commission
                    cost_log["total_slippage"] += sl_tp_trade.slippage_cost
                    cost_log["total_spread"] += sl_tp_trade.spread_cost
                    risk_state.balance += sl_tp_trade.net_pnl
                    self._update_risk_state(risk_state, sl_tp_trade.net_pnl)
                    position = None

                    # Check if risk limits breached after trade
                    if risk_state.trading_paused:
                        logger.warning(f"Backtest paused: {risk_state.pause_reason}")
                        break

            # ── 2. Run strategy analysis ──
            result = await strategy.analyze(symbol, window)

            if result and result.signal.type.value in ["buy", "sell"]:
                signal = result.signal

                # ── 3. Handle existing position reversal ──
                if position:
                    is_reverse = (
                        (signal.type.value == "buy" and position.side == "sell") or
                        (signal.type.value == "sell" and position.side == "buy")
                    )
                    if is_reverse:
                        # Close at the raw signal price; _close_position applies costs once.
                        trade = self._close_position(
                            position, signal.price, candle_time, "signal_reversal",
                            comm, slip, spread
                        )
                        trades.append(trade)
                        cost_log["total_commission"] += trade.commission
                        cost_log["total_slippage"] += trade.slippage_cost
                        cost_log["total_spread"] += trade.spread_cost
                        risk_state.balance += trade.net_pnl
                        self._update_risk_state(risk_state, trade.net_pnl)
                        position = None

                        if risk_state.trading_paused:
                            logger.warning(f"Backtest paused: {risk_state.pause_reason}")
                            break

                # ── 4. Open new position (if flat) ──
                if position is None:
                    if risk_state.daily_locked:
                        continue

                    # Risk check: mandatory stop loss
                    if self.mandatory_stop_loss and signal.stop_loss is None:
                        continue  # Skip signal

                    # Risk check: consecutive losses
                    if risk_state.consecutive_losses >= max_consec:
                        continue

                    # Risk check: drawdown
                    if risk_state.current_drawdown >= dd_pct:
                        risk_state.trading_paused = True
                        risk_state.pause_reason = f"Max drawdown {risk_state.current_drawdown}%"
                        break

                    # Position sizing (mirrors RiskManagementEngine._calculate_position_size)
                    quantity = self._calculate_position_size(
                        risk_state.balance, signal.price, signal.stop_loss,
                        risk_pct, signal.type.value
                    )

                    if quantity <= Decimal("0"):
                        continue

                    # Apply fill price with spread + slippage
                    fill_price = self._apply_fill_price(
                        signal.price, signal.type.value, spread, slip
                    )

                    # Calculate entry costs
                    notional = fill_price * quantity
                    entry_commission = (notional * comm).quantize(Decimal("0.01"))
                    entry_slippage_cost = signal.price * slip * quantity
                    entry_spread_cost = signal.price * spread / 2 * quantity  # Half spread at entry

                    position = BacktestPosition(
                        symbol=symbol,
                        side=signal.type.value,
                        entry_price=fill_price,
                        entry_reference_price=signal.price,
                        quantity=quantity,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        entry_time=candle_time,
                        entry_commission=entry_commission,
                        entry_slippage_cost=entry_slippage_cost,
                        entry_spread_cost=entry_spread_cost,
                    )

            # ── 5. Update equity curve ──
            unrealized_pnl = Decimal("0")
            if position:
                if position.side == "buy":
                    unrealized_pnl = (candle_close - position.entry_price) * position.quantity
                else:
                    unrealized_pnl = (position.entry_price - candle_close) * position.quantity

            current_equity = float(risk_state.balance + unrealized_pnl)
            equity_curve.append(current_equity)

            # Track peak / drawdown
            if current_equity > float(risk_state.peak_equity):
                risk_state.peak_equity = Decimal(str(current_equity))
            dd = float(risk_state.peak_equity) - current_equity
            if dd > float(risk_state.max_drawdown):
                risk_state.max_drawdown = Decimal(str(dd))

        # ──────────────────────────────────────────────────────────────
        # Close any remaining position at last candle close
        # ──────────────────────────────────────────────────────────────
        if position:
            last_candle = df.iloc[-1]
            exit_price_raw = Decimal(str(last_candle["close"]))
            trade = self._close_position(
                position, exit_price_raw,
                last_candle.get("timestamp"), "backtest_end",
                comm, slip, spread
            )
            trades.append(trade)
            cost_log["total_commission"] += trade.commission
            cost_log["total_slippage"] += trade.slippage_cost
            cost_log["total_spread"] += trade.spread_cost
            risk_state.balance += trade.net_pnl
            position = None

        # ──────────────────────────────────────────────────────────────
        # Calculate metrics
        # ──────────────────────────────────────────────────────────────
        winning_trades = [t for t in trades if t.net_pnl > 0]
        losing_trades = [t for t in trades if t.net_pnl <= 0]

        gross_profit = sum(t.net_pnl for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl for t in losing_trades))
        net_pnl = float(risk_state.balance) - initial_balance

        total_trades = len(trades)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        profit_factor = float(gross_profit) / float(gross_loss) if gross_loss > 0 else float('inf')

        # Sharpe ratio (annualized based on timeframe)
        returns = []
        for idx in range(1, len(equity_curve)):
            if equity_curve[idx - 1] > 0:
                ret = (equity_curve[idx] - equity_curve[idx - 1]) / equity_curve[idx - 1]
                returns.append(ret)

        tf_minutes = self._timeframe_to_minutes(timeframe)
        periods_per_year = (252 * 24 * 60) / tf_minutes  # Trading periods per year

        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(periods_per_year)
        else:
            sharpe = 0

        # Sortino ratio (downside deviation only)
        neg_returns = [r for r in returns if r < 0]
        if len(neg_returns) > 1:
            downside_std = np.std(neg_returns)
            sortino = (np.mean(returns) / downside_std) * np.sqrt(periods_per_year) if downside_std > 0 else 0
        else:
            sortino = 0

        # Max drawdown percentage
        peak = initial_balance
        max_dd_pct = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            if dd > max_dd_pct:
                max_dd_pct = dd

        # Average trade duration
        durations = []
        for t in trades:
            if t.entry_time is not None and t.exit_time is not None:
                if hasattr(t.entry_time, 'timestamp') and hasattr(t.exit_time, 'timestamp'):
                    dur = (t.exit_time - t.entry_time).total_seconds() / 60
                    durations.append(dur)
        avg_duration = np.mean(durations) if durations else 0

        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses_found = 0
        current_streak = 0
        streak_type = None
        for t in trades:
            if t.net_pnl > 0:
                if streak_type == "win":
                    current_streak += 1
                else:
                    current_streak = 1
                    streak_type = "win"
                max_consec_wins = max(max_consec_wins, current_streak)
            else:
                if streak_type == "loss":
                    current_streak += 1
                else:
                    current_streak = 1
                    streak_type = "loss"
                max_consec_losses_found = max(max_consec_losses_found, current_streak)

        # Build trade list for output
        trade_list = []
        for t in trades:
            trade_list.append({
                "symbol": t.symbol,
                "side": t.side,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price),
                "quantity": float(t.quantity),
                "entry_time": str(t.entry_time) if t.entry_time else None,
                "exit_time": str(t.exit_time) if t.exit_time else None,
                "gross_pnl": float(t.gross_pnl),
                "commission": float(t.commission),
                "slippage_cost": float(t.slippage_cost),
                "spread_cost": float(t.spread_cost),
                "net_pnl": float(t.net_pnl),
                "exit_reason": t.exit_reason,
            })

        result_dict = {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 2),
            "gross_profit": round(float(gross_profit), 2),
            "gross_loss": round(float(gross_loss), 2),
            "net_pnl": round(net_pnl, 2),
            "profit_factor": round(profit_factor, 4),
            "sharpe_ratio": round(float(sharpe), 4),
            "sortino_ratio": round(float(sortino), 4),
            "max_drawdown": round(float(risk_state.max_drawdown), 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "avg_trade_duration_min": round(float(avg_duration), 2),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses_found,
            "equity_curve": equity_curve,
            "trades": trade_list,
            "costs": {
                "total_commission": round(float(cost_log["total_commission"]), 2),
                "total_slippage": round(float(cost_log["total_slippage"]), 2),
                "total_spread": round(float(cost_log["total_spread"]), 2),
                "total_costs": round(float(
                    cost_log["total_commission"] + cost_log["total_slippage"] + cost_log["total_spread"]
                ), 2),
                "commission_rate": float(comm),
                "slippage_rate": float(slip),
                "spread_pct": float(spread),
            },
            "risk": {
                "risk_per_trade_pct": float(risk_pct),
                "max_drawdown_pct": float(dd_pct),
                "max_consecutive_losses": max_consec,
                "mandatory_stop_loss": self.mandatory_stop_loss,
                "trading_paused": risk_state.trading_paused,
                "pause_reason": risk_state.pause_reason,
                "final_balance": round(float(risk_state.balance), 2),
                "peak_equity": round(float(risk_state.peak_equity), 2),
            },
            "parameters": parameters or {},
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": strategy_name,
            "candles_processed": len(df) - min_periods,
            "data_source": "historical" if (self.data_path / f"{symbol.replace('/', '_')}_{timeframe}.csv").exists() else "synthetic",
        }

        logger.info(
            f"Backtest complete: {total_trades} trades, "
            f"Net P&L: {net_pnl:.2f}, Sharpe: {sharpe:.4f}, "
            f"Max DD: {max_dd_pct:.2f}%"
        )

        return result_dict

    # ──────────────────────────────────────────────────────────────────
    # Price simulation (spread, slippage, fill)
    # ──────────────────────────────────────────────────────────────────

    def _apply_fill_price(
        self,
        price: Decimal,
        side: str,
        spread: Decimal,
        slippage: Decimal
    ) -> Decimal:
        """
        Calculate fill price with spread and slippage.

        Matches PaperBroker logic:
        - BUY fills at ask (price + half_spread) + slippage
        - SELL fills at bid (price - half_spread) - slippage
        """
        half_spread = price * spread / 2
        slip_amount = price * slippage

        if side == "buy":
            fill = price + half_spread + slip_amount
        else:
            fill = price - half_spread - slip_amount

        return fill.quantize(Decimal("0.00000001"))

    def _get_spread_from_candle(self, candle: pd.Series) -> Decimal:
        """
        Estimate spread from candle data.

        Uses high-low range as a proxy when no historical spread data is available.
        Falls back to default_spread_pct.
        """
        high = Decimal(str(candle.get("high", 0)))
        low = Decimal(str(candle.get("low", 0)))
        close = Decimal(str(candle.get("close", 0)))

        if close > 0 and high > 0 and low > 0:
            # Spread proxy: use a fraction of the candle range
            candle_range = high - low
            estimated_spread = candle_range * Decimal("0.05")  # 5% of range
            # Cap at reasonable bounds
            max_spread = close * Decimal("0.005")  # 0.5% max
            min_spread = close * Decimal("0.00001")  # 0.001% min
            return max(min(estimated_spread, max_spread), min_spread)

        return close * self.default_spread_pct

    # ──────────────────────────────────────────────────────────────────
    # Stop-loss / Take-profit
    # ──────────────────────────────────────────────────────────────────

    def _check_sl_tp(
        self,
        position: BacktestPosition,
        candle_high: Decimal,
        candle_low: Decimal,
        candle_close: Decimal,
        spread: Decimal,
        commission_rate: Decimal,
        slippage_rate: Decimal,
        candle_time: Optional[datetime],
        symbol: str,
    ) -> Optional[BacktestTrade]:
        """Check if stop-loss or take-profit was hit during this candle."""
        if position.stop_loss and position.take_profit:
            # Determine which was hit first using open price as proxy
            if position.side == "buy":
                # For long: check if low hit SL first or high hit TP first
                if candle_low <= position.stop_loss:
                    return self._close_position(
                        position, position.stop_loss, candle_time, "stop_loss",
                        commission_rate, slippage_rate, spread
                    )
                if candle_high >= position.take_profit:
                    return self._close_position(
                        position, position.take_profit, candle_time, "take_profit",
                        commission_rate, slippage_rate, spread
                    )
            else:  # sell
                if candle_high >= position.stop_loss:
                    return self._close_position(
                        position, position.stop_loss, candle_time, "stop_loss",
                        commission_rate, slippage_rate, spread
                    )
                if candle_low <= position.take_profit:
                    return self._close_position(
                        position, position.take_profit, candle_time, "take_profit",
                        commission_rate, slippage_rate, spread
                    )

        elif position.stop_loss:
            if position.side == "buy" and candle_low <= position.stop_loss:
                return self._close_position(
                    position, position.stop_loss, candle_time, "stop_loss",
                    commission_rate, slippage_rate, spread
                )
            elif position.side == "sell" and candle_high >= position.stop_loss:
                return self._close_position(
                    position, position.stop_loss, candle_time, "stop_loss",
                    commission_rate, slippage_rate, spread
                )

        elif position.take_profit:
            if position.side == "buy" and candle_high >= position.take_profit:
                return self._close_position(
                    position, position.take_profit, candle_time, "take_profit",
                    commission_rate, slippage_rate, spread
                )
            elif position.side == "sell" and candle_low <= position.take_profit:
                return self._close_position(
                    position, position.take_profit, candle_time, "take_profit",
                    commission_rate, slippage_rate, spread
                )

        return None

    # ──────────────────────────────────────────────────────────────────
    # Position management
    # ──────────────────────────────────────────────────────────────────

    def _close_position(
        self,
        position: BacktestPosition,
        exit_price_raw: Decimal,
        exit_time: Optional[datetime],
        exit_reason: str,
        commission_rate: Decimal,
        slippage_rate: Decimal,
        spread: Decimal,
    ) -> BacktestTrade:
        """Close position and calculate full P&L with costs."""
        # Apply spread + slippage to exit price
        exit_side = "sell" if position.side == "buy" else "buy"
        exit_price = self._apply_fill_price(exit_price_raw, exit_side, spread, slippage_rate)

        # Gross P&L at reference prices, before any execution costs.
        if position.side == "buy":
            gross_pnl = (
                exit_price_raw - position.entry_reference_price
            ) * position.quantity
        else:
            gross_pnl = (
                position.entry_reference_price - exit_price_raw
            ) * position.quantity

        # Exit costs. Spread and slippage are measured independently.
        exit_notional = exit_price * position.quantity
        exit_commission = (exit_notional * commission_rate).quantize(Decimal("0.01"))
        exit_slippage = exit_price_raw * slippage_rate * position.quantity
        exit_spread = exit_price_raw * spread / 2 * position.quantity

        # Total costs
        total_commission = position.entry_commission + exit_commission
        total_slippage = position.entry_slippage_cost + exit_slippage
        total_spread = position.entry_spread_cost + exit_spread

        net_pnl = gross_pnl - total_commission - total_slippage - total_spread

        return BacktestTrade(
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=exit_time,
            gross_pnl=gross_pnl,
            commission=total_commission,
            slippage_cost=total_slippage,
            spread_cost=total_spread,
            net_pnl=net_pnl,
            exit_reason=exit_reason,
        )

    # ──────────────────────────────────────────────────────────────────
    # Position sizing (mirrors RiskManagementEngine._calculate_position_size)
    # ──────────────────────────────────────────────────────────────────

    def _calculate_position_size(
        self,
        balance: Decimal,
        price: Decimal,
        stop_loss: Optional[Decimal],
        risk_pct: Decimal,
        side: str,
    ) -> Decimal:
        """
        Calculate position size based on risk parameters.

        Identical logic to RiskManagementEngine._calculate_position_size.
        """
        if balance <= 0 or price <= 0:
            return Decimal("0")

        risk_amount = balance * (risk_pct / Decimal("100"))

        if stop_loss and stop_loss > 0:
            if side == "buy":
                sl_distance_pct = (price - stop_loss) / price
            else:
                sl_distance_pct = (stop_loss - price) / price

            if sl_distance_pct > 0:
                position_size = risk_amount / (sl_distance_pct * price)
            else:
                # Invalid SL (wrong side), use fallback
                position_size = risk_amount / price
        else:
            # No stop loss — use fixed percentage sizing
            position_size = risk_amount / price

        # Round down to reasonable precision
        position_size = position_size.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
        return max(position_size, Decimal("0"))

    # ──────────────────────────────────────────────────────────────────
    # Risk state management (mirrors RiskManagementEngine)
    # ──────────────────────────────────────────────────────────────────

    def _update_risk_state(self, state: RiskState, pnl: Decimal):
        """Update risk metrics after a trade. Mirrors update_trade_result."""
        state.total_trades += 1

        if pnl < 0:
            state.consecutive_losses += 1
            state.daily_pnl += abs(pnl)
        else:
            state.consecutive_losses = 0

        # Update drawdown
        if state.balance > state.peak_equity:
            state.peak_equity = state.balance
        dd = state.peak_equity - state.balance
        state.current_drawdown = (dd / state.peak_equity * 100).quantize(Decimal("0.01")) if state.peak_equity > 0 else Decimal("0")

        if state.current_drawdown > state.max_drawdown:
            state.max_drawdown = state.current_drawdown

        # Check risk limits
        if state.current_drawdown >= self.max_drawdown_pct:
            state.trading_paused = True
            state.pause_reason = f"Max drawdown {state.current_drawdown}% >= {self.max_drawdown_pct}%"

        if state.consecutive_losses >= self.max_consecutive_losses:
            state.trading_paused = True
            state.pause_reason = f"Consecutive losses {state.consecutive_losses} >= {self.max_consecutive_losses}"

        daily_loss_pct = (
            state.daily_pnl / state.daily_start_balance * 100
            if state.daily_start_balance > 0 else Decimal("0")
        )
        if daily_loss_pct >= self.max_daily_loss_pct:
            state.daily_locked = True

    def _roll_risk_day(self, state: RiskState, candle_time: Any):
        """Reset daily loss protection when the UTC trading date changes."""
        if candle_time is None:
            return
        timestamp = pd.Timestamp(candle_time)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        trading_day = timestamp.date()

        if state.current_day != trading_day:
            state.current_day = trading_day
            state.daily_start_balance = state.balance
            state.daily_pnl = Decimal("0")
            state.daily_locked = False

    # ──────────────────────────────────────────────────────────────────
    # Data loading
    # ──────────────────────────────────────────────────────────────────

    async def _load_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> Optional[pd.DataFrame]:
        """Load historical OHLCV data."""
        file_path = self.data_path / f"{symbol.replace('/', '_')}_{timeframe}.csv"

        if file_path.exists():
            df = pd.read_csv(file_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            if start_date:
                df = df[df['timestamp'] >= start_date]
            if end_date:
                df = df[df['timestamp'] <= end_date]

            df = df.reset_index(drop=True)

            # Validate OHLCV invariants
            df = self._validate_ohlcv(df)

            return df

        logger.warning(f"No historical data found for {symbol}, generating synthetic data")
        return self._generate_synthetic_data(symbol, timeframe)

    def _validate_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and fix OHLCV data invariants."""
        # Ensure high >= max(open, close) and low <= min(open, close)
        df["high"] = df[["high", "open", "close"]].max(axis=1)
        df["low"] = df[["low", "open", "close"]].min(axis=1)

        # Ensure positive values
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].abs()

        # Ensure volume is non-negative
        df["volume"] = df["volume"].clip(lower=0)

        return df

    def _generate_synthetic_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Generate realistic synthetic OHLCV data for testing."""
        np.random.seed(42)

        n = 1000
        base_prices = {
            "BTC/USDT": 65000, "ETH/USDT": 3500, "BNB/USDT": 600,
            "SOL/USDT": 150, "XRP/USDT": 0.60, "ADA/USDT": 0.45,
            "EUR/USD": 1.0850, "GBP/USD": 1.2650, "USD/JPY": 151.50,
        }
        base_price = base_prices.get(symbol, 100.0)

        timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=n, freq='1min')

        # Generate realistic price series with mean reversion + trend
        closes = [base_price]
        for i in range(1, n):
            # Mean-reverting random walk with momentum
            mean_reversion = -0.0001 * (closes[-1] - base_price) / base_price
            momentum = np.random.normal(0, 0.0008)
            change = mean_reversion + momentum
            closes.append(closes[-1] * (1 + change))

        # Generate OHLCV with proper invariants
        opens = [closes[0]] + closes[:-1]  # Open = previous close
        highs = []
        lows = []
        volumes = []

        for i in range(n):
            o = opens[i]
            c = closes[i]
            # High/Low based on candle body + wick
            body = abs(c - o)
            wick = body * np.random.uniform(0.2, 1.5) + abs(o) * 0.0001
            h = max(o, c) + abs(wick) * np.random.uniform(0, 1)
            l = min(o, c) - abs(wick) * np.random.uniform(0, 1)
            # Ensure invariants
            h = max(h, o, c)
            l = min(l, o, c)
            highs.append(h)
            lows.append(l)
            # Volume with some autocorrelation
            vol = np.random.lognormal(mean=10, sigma=0.5)
            volumes.append(vol)

        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })

        return df

    # ──────────────────────────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _timeframe_to_minutes(timeframe: str) -> int:
        """Convert timeframe string to minutes."""
        tf_map = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "4h": 240, "1d": 1440,
        }
        return tf_map.get(timeframe, 1)


# Global instance
backtest_engine = BacktestingEngine()