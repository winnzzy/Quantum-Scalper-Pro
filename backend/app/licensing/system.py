"""Licensing System - Commercial license management.

Features:
- License key generation and validation
- Subscription plan management
- Machine binding
- Usage tracking
- Affiliate system
"""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from app.core.config import settings
from app.core.logging import logger
from app.core.redis import redis_client


class LicensingSystem:
    """License management system."""

    def __init__(self):
        self.license_server_url = settings.LICENSE_SERVER_URL

    def generate_license_key(self, plan: str, duration_days: int = 365) -> str:
        """Generate a new license key."""
        # Generate random key
        random_part = secrets.token_urlsafe(16)
        plan_hash = hashlib.sha256(plan.encode()).hexdigest()[:8]

        license_key = f"QSP-{plan_hash.upper()}-{random_part.upper()}"
        return license_key

    async def validate_license(self, license_key: str, machine_id: str) -> Dict[str, Any]:
        """
        Validate license key.

        Returns:
            {
                "valid": bool,
                "plan": str,
                "expires_at": datetime,
                "features": list,
                "max_accounts": int,
                "max_strategies": int
            }
        """
        # Check cache first
        cache_key = f"license:{license_key}"
        cached = await redis_client.get_json(cache_key)

        if cached:
            return cached

        # In production, this would validate against a license server
        # For now, validate locally
        if not license_key.startswith("QSP-"):
            return {"valid": False, "reason": "Invalid license format"}

        # Extract plan from key
        parts = license_key.split("-")
        if len(parts) < 2:
            return {"valid": False, "reason": "Invalid license format"}

        plan_hash = parts[1].lower()
        plan_map = {
            "free": "free",
            "basic": "basic", 
            "pro": "pro",
            "enterprise": "enterprise"
        }

        # Determine plan from hash (simplified)
        plan = "pro"  # Default for demo

        result = {
            "valid": True,
            "plan": plan,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            "features": self._get_plan_features(plan),
            "max_accounts": 3 if plan == "pro" else 1,
            "max_strategies": 10 if plan == "pro" else 3,
            "machine_id": machine_id
        }

        # Cache result
        await redis_client.set_json(cache_key, result, expire=3600)

        return result

    def _get_plan_features(self, plan: str) -> list:
        """Get features for subscription plan."""
        features = {
            "free": [
                "paper_trading",
                "basic_strategies",
                "limited_backtesting"
            ],
            "basic": [
                "paper_trading",
                "live_trading",
                "basic_strategies",
                "email_notifications",
                "backtesting"
            ],
            "pro": [
                "paper_trading",
                "live_trading",
                "all_strategies",
                "ai_filter",
                "news_filter",
                "telegram_notifications",
                "advanced_analytics",
                "backtesting",
                "optimization",
                "multiple_brokers"
            ],
            "enterprise": [
                "all_pro_features",
                "custom_strategies",
                "white_label",
                "api_access",
                "dedicated_support",
                "unlimited_accounts"
            ]
        }
        return features.get(plan, features["free"])

    async def check_feature_access(self, license_key: str, feature: str) -> bool:
        """Check if license has access to a feature."""
        validation = await self.validate_license(license_key, "")
        if not validation["valid"]:
            return False

        features = validation.get("features", [])
        return feature in features

    async def record_usage(self, license_key: str, trades: int = 0, api_calls: int = 0):
        """Record license usage."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"usage:{license_key}:{today}"

        await redis_client.hset(key, "trades", str(trades))
        await redis_client.hset(key, "api_calls", str(api_calls))
        await redis_client._client.expire(key, 86400 * 30)  # Keep 30 days


# Global instance
licensing_system = LicensingSystem()
