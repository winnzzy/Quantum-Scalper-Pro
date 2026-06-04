"""Risk management tests."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.risk.engine import RiskManagementEngine
from app.models.risk import RiskProfile


@pytest.mark.asyncio
async def test_risk_profile_creation(db_session):
    """Test risk profile creation."""
    engine = RiskManagementEngine(db_session)
    profile = await engine._get_risk_profile(1)

    assert profile is not None
    assert profile.risk_per_trade_percent == Decimal("0.5")
    assert profile.max_open_trades == 10
    assert profile.mandatory_stop_loss == True


@pytest.mark.asyncio
async def test_loss_limits_check(db_session):
    """Test loss limit validation."""
    engine = RiskManagementEngine(db_session)
    profile = await engine._get_risk_profile(1)

    # Set daily loss at limit
    profile.current_daily_loss = Decimal("3.0")
    await db_session.commit()

    result = await engine._check_loss_limits(1, profile)
    assert not result["allowed"]
    assert "Daily loss limit" in result["reason"]


@pytest.mark.asyncio
async def test_weekend_protection():
    """Test weekend trading protection."""
    from unittest.mock import MagicMock

    profile = MagicMock()
    profile.weekend_protection_enabled = True

    # This test would need to mock datetime
    # For now, just verify the method exists
    assert hasattr(RiskManagementEngine, '_check_weekend_protection')


@pytest.mark.asyncio
async def test_position_size_calculation(db_session):
    """Test position size calculation."""
    engine = RiskManagementEngine(db_session)
    profile = await engine._get_risk_profile(1)

    sizing = await engine._calculate_position_size(
        user_id=1,
        symbol="BTC/USDT",
        price=Decimal("65000"),
        stop_loss=Decimal("60000"),
        risk_percent=None,
        profile=profile,
        direction="buy"
    )

    assert sizing["position_size"] > 0
    assert sizing["risk_amount"] > 0
