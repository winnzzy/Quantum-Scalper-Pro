"""Breakout Scalper Strategy."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

from app.strategies.base import BaseStrategy, Signal, SignalType, StrategyResult


class BreakoutScalper(BaseStrategy):
    """
    Breakout Scalper Strategy.

    Indicators:
    - Support/Resistance levels
    - Volume confirmation
    - ATR (Volatility)

    Entry Rules:
    - BUY: Price breaks above resistance with volume > 1.5x average
    - SELL: Price breaks below support with volume > 1.5x average
    """

    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            "lookback_period": 20,
            "volume_threshold": 1.5,
            "atr_period": 14,
            "atr_multiplier_sl": 2.0,
            "atr_multiplier_tp": 3.0,
            "min_breakout_pct": 0.001,  # 0.1%
            "confirmation_bars": 1,
        }
        if config:
            default_config.update(config)
        super().__init__("Breakout_Scalper", default_config)

    async def analyze(self, symbol: str, ohlcv_data: pd.DataFrame) -> Optional[StrategyResult]:
        if not self.validate_data(ohlcv_data, min_periods=30):
            return None

        df = ohlcv_data.copy()
        lookback = self.config["lookback_period"]

        # Calculate support/resistance
        df["resistance"] = df["high"].rolling(window=lookback).max()
        df["support"] = df["low"].rolling(window=lookback).min()
        df["volume_ma"] = df["volume"].rolling(window=20).mean()
        df["atr"] = self.calculate_atr(df, self.config["atr_period"])

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = Decimal(str(latest["close"]))
        resistance = Decimal(str(latest["resistance"]))
        support = Decimal(str(latest["support"]))
        atr = Decimal(str(latest["atr"]))
        volume = latest["volume"]
        vol_avg = latest["volume_ma"]

        min_breakout = Decimal(str(self.config["min_breakout_pct"]))
        vol_threshold = self.config["volume_threshold"]

        signal = None

        # Breakout above resistance
        if prev["close"] <= prev["resistance"] and latest["close"] > latest["resistance"]:
            breakout_pct = (price - resistance) / resistance
            if breakout_pct >= min_breakout and vol_avg > 0 and volume / vol_avg >= vol_threshold:
                confidence = self._calculate_confidence(df, "buy")
                sl = price - atr * Decimal(str(self.config["atr_multiplier_sl"]))
                tp = price + atr * Decimal(str(self.config["atr_multiplier_tp"]))

                signal = Signal(
                    type=SignalType.BUY,
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    price=price,
                    confidence=confidence,
                    indicators={
                        "resistance": float(latest["resistance"]),
                        "support": float(latest["support"]),
                        "breakout_pct": float(breakout_pct),
                        "volume_ratio": float(volume / vol_avg),
                        "atr": float(latest["atr"])
                    },
                    stop_loss=sl,
                    take_profit=tp,
                    reason=f"Breakout above resistance with {volume/vol_avg:.1f}x volume",
                    timeframe="1m"
                )

        # Breakdown below support
        elif prev["close"] >= prev["support"] and latest["close"] < latest["support"]:
            breakout_pct = (support - price) / support
            if breakout_pct >= min_breakout and vol_avg > 0 and volume / vol_avg >= vol_threshold:
                confidence = self._calculate_confidence(df, "sell")
                sl = price + atr * Decimal(str(self.config["atr_multiplier_sl"]))
                tp = price - atr * Decimal(str(self.config["atr_multiplier_tp"]))

                signal = Signal(
                    type=SignalType.SELL,
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    price=price,
                    confidence=confidence,
                    indicators={
                        "resistance": float(latest["resistance"]),
                        "support": float(latest["support"]),
                        "breakout_pct": float(breakout_pct),
                        "volume_ratio": float(volume / vol_avg),
                        "atr": float(latest["atr"])
                    },
                    stop_loss=sl,
                    take_profit=tp,
                    reason=f"Breakdown below support with {volume/vol_avg:.1f}x volume",
                    timeframe="1m"
                )

        if signal:
            self.last_signal = signal
            return StrategyResult(signal=signal, raw_data=df)

        return None

    def get_required_indicators(self) -> list:
        return ["support_resistance", "volume", "atr"]

    def _calculate_confidence(self, df: pd.DataFrame, direction: str) -> float:
        latest = df.iloc[-1]
        vol_ratio = latest["volume"] / latest["volume_ma"] if latest["volume_ma"] > 0 else 1

        # Volume score
        vol_score = min((vol_ratio - 1) * 0.4, 0.5)

        # Breakout strength
        if direction == "buy":
            breakout = (latest["close"] - latest["resistance"]) / latest["resistance"]
        else:
            breakout = (latest["support"] - latest["close"]) / latest["support"]

        breakout_score = min(breakout * 100, 0.3)

        # ATR confirmation
        atr_pct = latest["atr"] / latest["close"]
        atr_score = min(atr_pct / 0.001, 0.2)

        return round(min(vol_score + breakout_score + atr_score, 1.0), 4)
