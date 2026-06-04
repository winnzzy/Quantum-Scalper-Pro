"""Mean Reversion Scalper Strategy."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

from app.strategies.base import BaseStrategy, Signal, SignalType, StrategyResult


class MeanReversionScalper(BaseStrategy):
    """
    Mean Reversion Scalper Strategy.

    Indicators:
    - Bollinger Bands
    - RSI
    - Stochastic Oscillator

    Entry Rules:
    - BUY: Price touches lower Bollinger Band, RSI < 30, Stochastic < 20
    - SELL: Price touches upper Bollinger Band, RSI > 70, Stochastic > 80
    """

    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "stoch_k": 14,
            "stoch_d": 3,
            "stoch_oversold": 20,
            "stoch_overbought": 80,
            "atr_period": 14,
            "atr_multiplier_sl": 1.5,
            "atr_multiplier_tp": 2.0,
        }
        if config:
            default_config.update(config)
        super().__init__("MeanReversion_Scalper", default_config)

    async def analyze(self, symbol: str, ohlcv_data: pd.DataFrame) -> Optional[StrategyResult]:
        if not self.validate_data(ohlcv_data, min_periods=50):
            return None

        df = ohlcv_data.copy()

        # Calculate indicators
        upper, middle, lower = self.calculate_bollinger_bands(
            df["close"], 
            self.config["bb_period"], 
            self.config["bb_std"]
        )
        df["bb_upper"] = upper
        df["bb_middle"] = middle
        df["bb_lower"] = lower
        df["rsi"] = self.calculate_rsi(df["close"], self.config["rsi_period"])
        df["stoch_k"], df["stoch_d"] = self.calculate_stochastic(
            df["high"], df["low"], df["close"],
            self.config["stoch_k"], self.config["stoch_d"]
        )
        df["atr"] = self.calculate_atr(df, self.config["atr_period"])

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = Decimal(str(latest["close"]))
        atr = Decimal(str(latest["atr"]))
        rsi = latest["rsi"]
        stoch_k = latest["stoch_k"]

        signal = None

        # Buy: Oversold conditions
        if (latest["close"] <= latest["bb_lower"] or prev["close"] <= prev["bb_lower"]) and            rsi < self.config["rsi_oversold"] and stoch_k < self.config["stoch_oversold"]:

            confidence = self._calculate_confidence(latest, "buy")
            sl = price - atr * Decimal(str(self.config["atr_multiplier_sl"]))
            tp = price + atr * Decimal(str(self.config["atr_multiplier_tp"]))

            signal = Signal(
                type=SignalType.BUY,
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                price=price,
                confidence=confidence,
                indicators={
                    "bb_lower": float(latest["bb_lower"]),
                    "bb_upper": float(latest["bb_upper"]),
                    "rsi": float(rsi),
                    "stoch_k": float(stoch_k),
                    "atr": float(latest["atr"])
                },
                stop_loss=sl,
                take_profit=tp,
                reason="Mean reversion: Price at lower BB, RSI and Stochastic oversold",
                timeframe="1m"
            )

        # Sell: Overbought conditions
        elif (latest["close"] >= latest["bb_upper"] or prev["close"] >= prev["bb_upper"]) and              rsi > self.config["rsi_overbought"] and stoch_k > self.config["stoch_overbought"]:

            confidence = self._calculate_confidence(latest, "sell")
            sl = price + atr * Decimal(str(self.config["atr_multiplier_sl"]))
            tp = price - atr * Decimal(str(self.config["atr_multiplier_tp"]))

            signal = Signal(
                type=SignalType.SELL,
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                price=price,
                confidence=confidence,
                indicators={
                    "bb_lower": float(latest["bb_lower"]),
                    "bb_upper": float(latest["bb_upper"]),
                    "rsi": float(rsi),
                    "stoch_k": float(stoch_k),
                    "atr": float(latest["atr"])
                },
                stop_loss=sl,
                take_profit=tp,
                reason="Mean reversion: Price at upper BB, RSI and Stochastic overbought",
                timeframe="1m"
            )

        if signal:
            self.last_signal = signal
            return StrategyResult(signal=signal, raw_data=df)

        return None

    def get_required_indicators(self) -> list:
        return ["bollinger_bands", "rsi", "stochastic"]

    def _calculate_confidence(self, latest: pd.Series, direction: str) -> float:
        rsi = latest["rsi"]
        stoch = latest["stoch_k"]

        if direction == "buy":
            rsi_score = min((self.config["rsi_oversold"] - rsi) / self.config["rsi_oversold"] * 0.4, 0.4)
            stoch_score = min((self.config["stoch_oversold"] - stoch) / self.config["stoch_oversold"] * 0.3, 0.3)
            # BB touch strength
            bb_dist = (latest["bb_lower"] - latest["close"]) / latest["close"] if latest["close"] < latest["bb_lower"] else 0
            bb_score = min(bb_dist * 100, 0.3)
        else:
            rsi_score = min((rsi - self.config["rsi_overbought"]) / (100 - self.config["rsi_overbought"]) * 0.4, 0.4)
            stoch_score = min((stoch - self.config["stoch_overbought"]) / (100 - self.config["stoch_overbought"]) * 0.3, 0.3)
            bb_dist = (latest["close"] - latest["bb_upper"]) / latest["close"] if latest["close"] > latest["bb_upper"] else 0
            bb_score = min(bb_dist * 100, 0.3)

        return round(min(rsi_score + stoch_score + bb_score, 1.0), 4)
