"""VWAP Scalper Strategy."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

from app.strategies.base import BaseStrategy, Signal, SignalType, StrategyResult
from app.core.logging import logger


class VWAPScalper(BaseStrategy):
    """
    VWAP Scalper Strategy.

    Indicators:
    - VWAP (Volume Weighted Average Price)
    - RSI (Momentum)
    - Volume Analysis

    Entry Rules:
    - BUY: Price pulls back to VWAP, RSI > 50, volume above average
    - SELL: Price rallies to VWAP, RSI < 50, volume above average
    """

    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            "vwap_deviation": 0.001,  # 0.1% deviation from VWAP
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "volume_ma_period": 20,
            "volume_threshold": 1.5,  # 1.5x average volume
            "atr_period": 14,
            "atr_multiplier_sl": 1.5,
            "atr_multiplier_tp": 2.0,
        }
        if config:
            default_config.update(config)
        super().__init__("VWAP_Scalper", default_config)

    async def analyze(self, symbol: str, ohlcv_data: pd.DataFrame) -> Optional[StrategyResult]:
        if not self.validate_data(ohlcv_data, min_periods=50):
            return None

        df = ohlcv_data.copy()

        # Calculate indicators
        df["vwap"] = self.calculate_vwap(df)
        df["rsi"] = self.calculate_rsi(df["close"], self.config["rsi_period"])
        df["volume_ma"] = df["volume"].rolling(window=self.config["volume_ma_period"]).mean()
        df["atr"] = self.calculate_atr(df, self.config["atr_period"])

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = Decimal(str(latest["close"]))
        vwap = Decimal(str(latest["vwap"]))
        atr = Decimal(str(latest["atr"]))
        rsi = latest["rsi"]
        volume = latest["volume"]
        vol_avg = latest["volume_ma"]

        # Volume check
        vol_threshold = self.config["volume_threshold"]
        if vol_avg > 0 and volume / vol_avg < vol_threshold:
            return None

        deviation = abs(price - vwap) / vwap
        max_deviation = Decimal(str(self.config["vwap_deviation"]))

        signal = None

        # Buy: Price near/below VWAP, RSI > 50 (momentum up)
        if price <= vwap * (Decimal("1") + max_deviation) and rsi > 50 and rsi < self.config["rsi_overbought"]:
            if prev["close"] <= prev["vwap"] and latest["close"] > latest["vwap"]:
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
                        "vwap": float(latest["vwap"]),
                        "rsi": float(latest["rsi"]),
                        "volume_ratio": float(volume / vol_avg) if vol_avg > 0 else 0,
                        "atr": float(latest["atr"])
                    },
                    stop_loss=sl,
                    take_profit=tp,
                    reason="Price bounced off VWAP with volume confirmation",
                    timeframe="1m"
                )

        # Sell: Price near/above VWAP, RSI < 50 (momentum down)
        elif price >= vwap * (Decimal("1") - max_deviation) and rsi < 50 and rsi > self.config["rsi_oversold"]:
            if prev["close"] >= prev["vwap"] and latest["close"] < latest["vwap"]:
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
                        "vwap": float(latest["vwap"]),
                        "rsi": float(latest["rsi"]),
                        "volume_ratio": float(volume / vol_avg) if vol_avg > 0 else 0,
                        "atr": float(latest["atr"])
                    },
                    stop_loss=sl,
                    take_profit=tp,
                    reason="Price rejected at VWAP with volume confirmation",
                    timeframe="1m"
                )

        if signal:
            self.last_signal = signal
            return StrategyResult(signal=signal, raw_data=df)

        return None

    def get_required_indicators(self) -> list:
        return ["vwap", "rsi", "volume"]

    def _calculate_confidence(self, latest: pd.Series, direction: str) -> float:
        rsi = latest["rsi"]
        vol_ratio = latest["volume"] / latest["volume_ma"] if latest["volume_ma"] > 0 else 1

        if direction == "buy":
            rsi_score = min((rsi - 50) / 20, 0.4)  # RSI 50-70 -> 0-0.4
        else:
            rsi_score = min((50 - rsi) / 20, 0.4)  # RSI 30-50 -> 0-0.4

        vol_score = min((vol_ratio - 1) * 0.3, 0.4)
        deviation = abs(latest["close"] - latest["vwap"]) / latest["vwap"]
        deviation_score = max(0, 0.2 - deviation * 100)

        return round(min(rsi_score + vol_score + deviation_score, 1.0), 4)
