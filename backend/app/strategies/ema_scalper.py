"""EMA Scalper Strategy."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

from app.strategies.base import BaseStrategy, Signal, SignalType, StrategyResult
from app.core.logging import logger


class EMAScalper(BaseStrategy):
    """
    EMA Scalper Strategy.

    Indicators:
    - EMA 9 (Fast)
    - EMA 21 (Medium)
    - EMA 50 (Slow/Trend)
    - ATR (Volatility)

    Entry Rules:
    - BUY: EMA9 crosses above EMA21, price above EMA50, ATR confirms volatility
    - SELL: EMA9 crosses below EMA21, price below EMA50, ATR confirms volatility
    """

    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            "ema_fast": 9,
            "ema_medium": 21,
            "ema_slow": 50,
            "atr_period": 14,
            "atr_multiplier_sl": 1.5,
            "atr_multiplier_tp": 2.5,
            "min_atr": 0.0005,  # Minimum ATR as % of price
            "trend_filter": True,
            "adx_period": 14,
            "min_adx": 20.0,
        }
        if config:
            default_config.update(config)
        super().__init__("EMA_Scalper", default_config)

    async def analyze(self, symbol: str, ohlcv_data: pd.DataFrame) -> Optional[StrategyResult]:
        """Analyze market data."""
        if not self.validate_data(ohlcv_data, min_periods=60):
            return None

        df = ohlcv_data.copy()

        # Calculate indicators
        ema_fast = self.config["ema_fast"]
        ema_medium = self.config["ema_medium"]
        ema_slow = self.config["ema_slow"]
        atr_period = self.config["atr_period"]

        df["ema_fast"] = self.calculate_ema(df["close"], ema_fast)
        df["ema_medium"] = self.calculate_ema(df["close"], ema_medium)
        df["ema_slow"] = self.calculate_ema(df["close"], ema_slow)
        df["atr"] = self.calculate_atr(df, atr_period)
        df["adx"] = self.calculate_adx(df, self.config["adx_period"])

        # Get latest values
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = Decimal(str(latest["close"]))
        atr = Decimal(str(latest["atr"]))
        adx = latest["adx"]

        # Require both tradable volatility and a directional market regime.
        if pd.isna(adx) or adx < self.config["min_adx"]:
            return None

        # Minimum ATR check
        min_atr_pct = Decimal(str(self.config["min_atr"]))
        if atr / price < min_atr_pct:
            return None

        # Trend filter
        trend_bullish = latest["close"] > latest["ema_slow"] if self.config["trend_filter"] else True
        trend_bearish = latest["close"] < latest["ema_slow"] if self.config["trend_filter"] else True

        # Crossover detection
        fast_cross_up = prev["ema_fast"] <= prev["ema_medium"] and latest["ema_fast"] > latest["ema_medium"]
        fast_cross_down = prev["ema_fast"] >= prev["ema_medium"] and latest["ema_fast"] < latest["ema_medium"]

        signal = None
        confidence = 0.0

        if fast_cross_up and trend_bullish:
            # Buy signal
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
                    "ema_fast": float(latest["ema_fast"]),
                    "ema_medium": float(latest["ema_medium"]),
                    "ema_slow": float(latest["ema_slow"]),
                    "atr": float(latest["atr"]),
                    "adx": float(adx),
                    "trend": "bullish"
                },
                stop_loss=sl,
                take_profit=tp,
                reason="EMA9 crossed above EMA21 with bullish trend",
                timeframe="1m"
            )

        elif fast_cross_down and trend_bearish:
            # Sell signal
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
                    "ema_fast": float(latest["ema_fast"]),
                    "ema_medium": float(latest["ema_medium"]),
                    "ema_slow": float(latest["ema_slow"]),
                    "atr": float(latest["atr"]),
                    "adx": float(adx),
                    "trend": "bearish"
                },
                stop_loss=sl,
                take_profit=tp,
                reason="EMA9 crossed below EMA21 with bearish trend",
                timeframe="1m"
            )

        if signal:
            self.last_signal = signal
            return StrategyResult(
                signal=signal,
                raw_data=df,
                metrics={
                    "confidence": confidence,
                    "atr": float(atr),
                    "adx": float(adx),
                    "market_regime": "trending",
                }
            )

        return None

    def get_required_indicators(self) -> list:
        return ["ema", "atr", "adx"]

    def _calculate_confidence(self, df: pd.DataFrame, direction: str) -> float:
        """Calculate signal confidence score (0-1)."""
        latest = df.iloc[-1]

        # Base confidence from EMA alignment
        ema_aligned = 0.0
        if direction == "buy":
            if latest["ema_fast"] > latest["ema_medium"] > latest["ema_slow"]:
                ema_aligned = 0.4
            elif latest["ema_fast"] > latest["ema_medium"]:
                ema_aligned = 0.2
        else:
            if latest["ema_fast"] < latest["ema_medium"] < latest["ema_slow"]:
                ema_aligned = 0.4
            elif latest["ema_fast"] < latest["ema_medium"]:
                ema_aligned = 0.2

        # ATR strength
        atr_pct = latest["atr"] / latest["close"]
        atr_score = min(atr_pct / 0.001, 0.3)  # Max 0.3 for 0.1% ATR

        # Volume confirmation
        vol_avg = df["volume"].rolling(20).mean().iloc[-1]
        vol_ratio = latest["volume"] / vol_avg if vol_avg > 0 else 1
        vol_score = min((vol_ratio - 1) * 0.15, 0.3) if vol_ratio > 1 else 0

        confidence = min(ema_aligned + atr_score + vol_score, 1.0)
        return round(confidence, 4)
