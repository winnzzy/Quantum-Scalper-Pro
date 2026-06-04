"""Base strategy class and common types."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum

import pandas as pd
import numpy as np


class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


@dataclass
class Signal:
    """Trading signal."""
    type: SignalType
    symbol: str
    timestamp: datetime
    price: Decimal
    confidence: float = 0.0
    indicators: Dict[str, Any] = field(default_factory=dict)
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    reason: str = ""
    timeframe: str = "1m"


@dataclass
class StrategyResult:
    """Strategy analysis result."""
    signal: Signal
    raw_data: pd.DataFrame
    metrics: Dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.is_active = True
        self.last_signal: Optional[Signal] = None

    @abstractmethod
    async def analyze(self, symbol: str, ohlcv_data: pd.DataFrame) -> Optional[StrategyResult]:
        """Analyze market data and generate signal."""
        pass

    @abstractmethod
    def get_required_indicators(self) -> List[str]:
        """Get list of required indicators."""
        pass

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    def calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_bollinger_bands(self, series: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple:
        """Calculate Bollinger Bands."""
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Volume Weighted Average Price."""
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()
        return vwap

    def calculate_stochastic(self, high: pd.Series, low: pd.Series, close: pd.Series, 
                            k_period: int = 14, d_period: int = 3) -> tuple:
        """Calculate Stochastic Oscillator."""
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()

        k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        d = k.rolling(window=d_period).mean()
        return k, d

    def validate_data(self, df: pd.DataFrame, min_periods: int = 50) -> bool:
        """Validate OHLCV data."""
        if df is None or len(df) < min_periods:
            return False
        required_cols = ["open", "high", "low", "close", "volume"]
        return all(col in df.columns for col in required_cols)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)
