"""Regime-aware strategy designed only for BTC/USDT and XAU/USD."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from app.core.markets import get_market
from app.strategies.base import BaseStrategy, Signal, SignalType, StrategyResult


class DualMarketRegimeStrategy(BaseStrategy):
    """Trade aligned trends after a pullback reclaim or confirmed breakout.

    The two instruments use separate defaults. Parameters remain candidates,
    not profitability claims; they must pass walk-forward validation on data
    from the intended execution venue before live use.
    """

    PROFILES: Dict[str, Dict[str, Any]] = {
        "BTC/USDT": {
            "ema_fast": 20, "ema_medium": 50, "ema_slow": 200,
            "adx_period": 14, "min_adx": 22.0, "rsi_period": 14,
            "long_rsi_min": 52.0, "long_rsi_max": 72.0,
            "short_rsi_min": 28.0, "short_rsi_max": 48.0,
            "breakout_lookback": 20, "min_volume_ratio": 1.10,
            "atr_period": 14, "min_atr_pct": 0.0015, "max_atr_pct": 0.018,
            "stop_atr": 1.8, "reward_risk": 2.2,
        },
        "XAU/USD": {
            "ema_fast": 20, "ema_medium": 50, "ema_slow": 200,
            "adx_period": 14, "min_adx": 20.0, "rsi_period": 14,
            "long_rsi_min": 50.0, "long_rsi_max": 68.0,
            "short_rsi_min": 32.0, "short_rsi_max": 50.0,
            "breakout_lookback": 24, "min_volume_ratio": 0.0,
            "atr_period": 14, "min_atr_pct": 0.0005, "max_atr_pct": 0.009,
            "stop_atr": 1.6, "reward_risk": 2.0,
        },
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("Dual_Market_Regime", config or {})

    async def analyze(self, symbol: str, ohlcv_data: pd.DataFrame) -> Optional[StrategyResult]:
        market = get_market(symbol)
        params = {**self.PROFILES[market.symbol], **self.config}
        required = max(220, int(params["ema_slow"]) + 5)
        if not self.validate_data(ohlcv_data, min_periods=required):
            return None

        df = ohlcv_data.copy()
        close = pd.to_numeric(df["close"], errors="coerce")
        volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
        df["ema_fast"] = self.calculate_ema(close, int(params["ema_fast"]))
        df["ema_medium"] = self.calculate_ema(close, int(params["ema_medium"]))
        df["ema_slow"] = self.calculate_ema(close, int(params["ema_slow"]))
        df["atr"] = self.calculate_atr(df, int(params["atr_period"]))
        df["adx"] = self.calculate_adx(df, int(params["adx_period"]))
        df["rsi"] = self.calculate_rsi(close, int(params["rsi_period"]))
        df["prior_high"] = df["high"].rolling(int(params["breakout_lookback"])).max().shift(1)
        df["prior_low"] = df["low"].rolling(int(params["breakout_lookback"])).min().shift(1)
        df["volume_ma"] = volume.rolling(20).mean().shift(1)

        latest, previous = df.iloc[-1], df.iloc[-2]
        values = [latest[key] for key in (
            "close", "ema_fast", "ema_medium", "ema_slow", "atr", "adx", "rsi",
            "prior_high", "prior_low",
        )]
        if any(pd.isna(value) or not np.isfinite(float(value)) for value in values):
            return None

        price = Decimal(str(latest["close"]))
        atr = Decimal(str(latest["atr"]))
        atr_pct = float(atr / price)
        if not float(params["min_atr_pct"]) <= atr_pct <= float(params["max_atr_pct"]):
            return None
        if float(latest["adx"]) < float(params["min_adx"]):
            return None

        volume_ratio = (
            float(latest["volume"] / latest["volume_ma"])
            if latest["volume_ma"] > 0 else 0.0
        )
        volume_ok = volume_ratio >= float(params["min_volume_ratio"])
        bullish = latest["ema_fast"] > latest["ema_medium"] > latest["ema_slow"]
        bearish = latest["ema_fast"] < latest["ema_medium"] < latest["ema_slow"]
        long_trigger = (
            previous["close"] <= previous["ema_fast"] and latest["close"] > latest["ema_fast"]
        ) or latest["close"] > latest["prior_high"]
        short_trigger = (
            previous["close"] >= previous["ema_fast"] and latest["close"] < latest["ema_fast"]
        ) or latest["close"] < latest["prior_low"]

        direction: Optional[SignalType] = None
        if (
            bullish and long_trigger and volume_ok
            and float(params["long_rsi_min"]) <= latest["rsi"] <= float(params["long_rsi_max"])
        ):
            direction = SignalType.BUY
        elif (
            bearish and short_trigger and volume_ok
            and float(params["short_rsi_min"]) <= latest["rsi"] <= float(params["short_rsi_max"])
        ):
            direction = SignalType.SELL
        if direction is None:
            return None

        risk_distance = atr * Decimal(str(params["stop_atr"]))
        reward_distance = risk_distance * Decimal(str(params["reward_risk"]))
        is_buy = direction is SignalType.BUY
        confidence = min(
            0.95,
            0.50 + min(float(latest["adx"]) / 100, 0.25)
            + min(max(volume_ratio - 1, 0) * 0.10, 0.10),
        )
        signal = Signal(
            type=direction,
            symbol=market.symbol,
            timestamp=datetime.now(timezone.utc),
            price=price,
            confidence=round(confidence, 4),
            indicators={
                "adx": float(latest["adx"]), "rsi": float(latest["rsi"]),
                "atr_pct": atr_pct, "volume_ratio": volume_ratio,
                "market_profile": market.asset_class,
            },
            stop_loss=price - risk_distance if is_buy else price + risk_distance,
            take_profit=price + reward_distance if is_buy else price - reward_distance,
            reason=f"{market.symbol} aligned regime with confirmed {'long' if is_buy else 'short'} trigger",
            timeframe=str(self.config.get("timeframe", market.default_timeframe)),
        )
        self.last_signal = signal
        return StrategyResult(
            signal=signal,
            raw_data=df,
            metrics={"market_regime": "trend", "reward_risk": float(params["reward_risk"])},
        )

    def get_required_indicators(self) -> list:
        return ["ema", "adx", "rsi", "atr", "volume", "breakout"]
