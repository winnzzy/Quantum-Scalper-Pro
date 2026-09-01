"""AI Filter Engine for trade quality scoring."""
import os
import pickle
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

from app.core.config import settings
from app.core.logging import logger
from app.strategies.base import Signal


class AIFilterEngine:
    """
    AI Filter Engine using XGBoost/LightGBM for trade quality scoring.

    Purpose: Filter bad trades, not generate them.
    Inputs: Volatility, Spread, Indicator Strength, Session Data, Volume
    Output: Trade Quality Score (0-1), Confidence Score (0-1)
    """

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.model_path = Path(settings.AI_MODEL_PATH)
        self.model_path.mkdir(parents=True, exist_ok=True)
        self.is_trained = False
        self._load_model()

    def _load_model(self):
        """Load pre-trained model if available."""
        model_file = self.model_path / "filter_model.pkl"
        scaler_file = self.model_path / "scaler.pkl"

        if model_file.exists() and scaler_file.exists():
            try:
                with open(model_file, "rb") as f:
                    self.model = pickle.load(f)
                with open(scaler_file, "rb") as f:
                    self.scaler = pickle.load(f)
                self.is_trained = True
                logger.info("AI Filter model loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
                self._init_default_model()
        else:
            self._init_default_model()

    def _init_default_model(self):
        """Initialize default model with conservative parameters."""
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        logger.info("AI Filter initialized with default model")

    def _extract_features(self, signal: Signal, market_data: Dict[str, Any]) -> np.ndarray:
        """Extract features from signal and market data."""
        indicators = signal.indicators
        price = price
        if not np.isfinite(price) or price <= 0:
            raise ValueError("Signal price must be a positive finite number")

        features = [
            # Volatility (ATR as % of price)
            float(indicators.get("atr", 0)) / price * 100,

            # Spread
            float(market_data.get("spread", 0)) / price * 100,

            # Indicator strength
            signal.confidence,

            # Volume ratio
            float(indicators.get("volume_ratio", 1)),

            # Session (hour of day)
            datetime.now(timezone.utc).hour / 24.0,

            # Day of week
            datetime.now(timezone.utc).weekday() / 7.0,

            # Price distance from key levels
            float(indicators.get("ema_fast", 0)) / price - 1 if "ema_fast" in indicators else 0,

            # RSI distance from extremes
            abs(50 - float(indicators.get("rsi", 50))) / 50 if "rsi" in indicators else 0,

            # Bollinger position
            float(indicators.get("bb_upper", 0)) / price - 1 if "bb_upper" in indicators else 0,

            # Trend strength
            1.0 if indicators.get("trend") == "bullish" and signal.type.value == "buy" else 
            1.0 if indicators.get("trend") == "bearish" and signal.type.value == "sell" else 0.5,
        ]

        return np.array(features).reshape(1, -1)

    def evaluate(self, signal: Signal, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate trade signal quality.

        Returns:
            {
                "quality_score": float (0-1),
                "confidence": float (0-1),
                "recommendation": "pass" | "caution" | "block",
                "reason": str,
                "features": dict
            }
        """
        if not settings.AI_FILTER_ENABLED:
            return {
                "quality_score": 1.0,
                "confidence": 1.0,
                "recommendation": "pass",
                "reason": "AI Filter disabled",
                "features": {}
            }

        try:
            features = self._extract_features(signal, market_data)

            # Rule-based pre-filtering (always active)
            rule_score = self._rule_based_score(signal, market_data)

            # Model prediction (if trained)
            if self.is_trained:
                scaled_features = self.scaler.transform(features)
                proba = self.model.predict_proba(scaled_features)[0]
                model_score = float(proba[1])  # Probability of good trade
            else:
                model_score = 0.5  # Neutral when not trained

            # Combine scores (60% rules, 40% model)
            quality_score = rule_score * 0.6 + model_score * 0.4

            # Confidence based on data quality
            confidence = min(signal.confidence * 0.5 + 0.5, 1.0)

            # Determine recommendation
            min_confidence = settings.AI_MIN_CONFIDENCE

            if quality_score >= 0.7 and confidence >= min_confidence:
                recommendation = "pass"
                reason = "High quality signal with strong confidence"
            elif quality_score >= 0.5 and confidence >= min_confidence * 0.8:
                recommendation = "caution"
                reason = "Moderate quality signal, proceed with caution"
            else:
                recommendation = "block"
                reason = f"Low quality signal (score: {quality_score:.2f}) or insufficient confidence ({confidence:.2f})"

            return {
                "quality_score": round(quality_score, 4),
                "confidence": round(confidence, 4),
                "recommendation": recommendation,
                "reason": reason,
                "features": {
                    "volatility_pct": float(features[0][0]),
                    "spread_pct": float(features[0][1]),
                    "indicator_strength": float(features[0][2]),
                    "volume_ratio": float(features[0][3]),
                    "session_hour": float(features[0][4]) * 24,
                    "rule_score": rule_score,
                    "model_score": model_score,
                }
            }

        except Exception as e:
            logger.error(f"AI Filter evaluation failed: {e}")
            return {
                "quality_score": 0.0,
                "confidence": 0.0,
                "recommendation": "block",
                "reason": f"Evaluation error: {str(e)}",
                "features": {}
            }

    def _rule_based_score(self, signal: Signal, market_data: Dict[str, Any]) -> float:
        """Calculate rule-based quality score."""
        score = 0.5  # Base score

        price = float(signal.price)
        if not np.isfinite(price) or price <= 0:
            return 0.0

        # Spread check
        spread_pct = float(market_data.get("spread", 0)) / price * 100
        if spread_pct > 0.05:  # > 0.05% spread
            score -= 0.3
        elif spread_pct < 0.01:
            score += 0.1

        # Volatility check
        atr_pct = float(signal.indicators.get("atr", 0)) / price * 100
        if atr_pct < 0.02:  # Too low volatility
            score -= 0.2
        elif 0.05 <= atr_pct <= 0.3:  # Good volatility range
            score += 0.2
        elif atr_pct > 0.5:  # Too high volatility
            score -= 0.2

        # Volume check
        vol_ratio = float(signal.indicators.get("volume_ratio", 1))
        if vol_ratio >= 1.5:
            score += 0.1
        elif vol_ratio < 0.5:
            score -= 0.1

        # Signal confidence
        score += (signal.confidence - 0.5) * 0.2

        # Time filter (avoid low liquidity hours)
        hour = datetime.now(timezone.utc).hour
        if hour in [22, 23, 0, 1, 2, 3, 4]:  # Low liquidity hours
            score -= 0.1

        return max(0.0, min(1.0, score))

    def train(self, features: np.ndarray, labels: np.ndarray) -> bool:
        """Train the model with historical data."""
        try:
            if len(features) < 100:
                logger.warning("Insufficient data for training (minimum 100 samples)")
                return False

            scaled_features = self.scaler.fit_transform(features)
            self.model.fit(scaled_features, labels)
            self.is_trained = True

            # Save model
            with open(self.model_path / "filter_model.pkl", "wb") as f:
                pickle.dump(self.model, f)
            with open(self.model_path / "scaler.pkl", "wb") as f:
                pickle.dump(self.scaler, f)

            logger.info("AI Filter model trained and saved")
            return True

        except Exception as e:
            logger.error(f"Model training failed: {e}")
            return False

    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """Get feature importance from model."""
        if not self.is_trained or not hasattr(self.model, "feature_importances_"):
            return None

        feature_names = [
            "volatility", "spread", "indicator_strength", "volume_ratio",
            "session_hour", "day_of_week", "price_distance", "rsi_distance",
            "bb_position", "trend_alignment"
        ]

        importances = self.model.feature_importances_
        return {name: float(imp) for name, imp in zip(feature_names, importances)}


# Global instance
ai_filter = AIFilterEngine()
