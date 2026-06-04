"""Risk Management API routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.models.user import User
from app.models.risk import RiskProfile
from app.risk.engine import RiskManagementEngine

router = APIRouter()


class RiskProfileUpdate(BaseModel):
    risk_per_trade_percent: float | None = None
    risk_per_trade_custom: float | None = None
    daily_loss_limit_percent: float | None = None
    weekly_loss_limit_percent: float | None = None
    monthly_loss_limit_percent: float | None = None
    max_drawdown_percent: float | None = None
    max_consecutive_losses: int | None = None
    max_open_trades: int | None = None
    spread_protection_enabled: bool | None = None
    volatility_protection_enabled: bool | None = None
    weekend_protection_enabled: bool | None = None
    news_protection_enabled: bool | None = None
    mandatory_stop_loss: bool | None = None


@router.get("/profile")
async def get_risk_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get risk profile."""
    engine = RiskManagementEngine(db)
    profile = await engine._get_risk_profile(current_user.id)
    return profile


@router.put("/profile")
async def update_risk_profile(
    update: RiskProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update risk profile."""
    result = await db.execute(
        select(RiskProfile).where(RiskProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Risk profile not found")

    update_data = update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            if isinstance(value, float):
                value = Decimal(str(value))
            setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("/pause")
async def pause_trading(
    reason: str = "Manual pause",
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Pause trading."""
    engine = RiskManagementEngine(db)
    success = await engine.pause_trading(current_user.id, reason)
    return {"paused": success, "reason": reason}


@router.post("/resume")
async def resume_trading(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Resume trading."""
    engine = RiskManagementEngine(db)
    success = await engine.resume_trading(current_user.id)
    return {"resumed": success}


@router.get("/events")
async def get_risk_events(
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get risk events."""
    from sqlalchemy import desc
    from app.models.risk import RiskEvent

    result = await db.execute(
        select(RiskEvent)
        .where(RiskEvent.user_id == current_user.id)
        .order_by(desc(RiskEvent.created_at))
        .limit(limit)
    )
    return result.scalars().all()
