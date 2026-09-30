"""System API routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.models.user import User
from app.models.system import Notification
from sqlalchemy import select, desc
from app.services.launch_readiness import private_launch_readiness
from app.core.config import settings
from app.engines.trading import trading_engine_manager
from app.core.operational_state import activate_emergency_stop, clear_emergency_stop
from app.core.security import verify_password
from app.auth.totp import decrypt_secret, verify_code

router = APIRouter()


class EmergencyResetRequest(BaseModel):
    current_password: str
    otp_code: str


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user notifications."""
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.is_read == False)

    query = query.order_by(desc(Notification.created_at)).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark notification as read."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
    )
    notification = result.scalar_one_or_none()

    if notification:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()

    return {"success": True}


@router.get("/health")
async def health_check():
    """Public health check."""
    return {"status": "healthy", "service": "Quantum Scalper Pro", "version": "1.0.0"}


@router.get("/launch-readiness")
async def launch_readiness(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return every evidence and safety gate required before live launch."""
    return await private_launch_readiness(db, current_user.id)


@router.post("/emergency-stop")
async def emergency_stop(current_user: User = Depends(get_current_active_user)):
    """Immediately block new orders and stop every in-process trading loop."""
    await activate_emergency_stop()
    await trading_engine_manager.stop_all()
    return {"emergency_stop": True, "message": "All trading engines stopped"}


@router.post("/emergency-stop/reset")
async def reset_emergency_stop(
    payload: EmergencyResetRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Clear the durable stop only after password and authenticator verification."""
    secret = decrypt_secret(current_user.two_factor_secret or "")
    if (
        not current_user.two_factor_enabled
        or not verify_password(payload.current_password, current_user.hashed_password)
        or not secret
        or not verify_code(secret, payload.otp_code)
    ):
        raise HTTPException(status_code=403, detail="Password and authenticator verification failed")
    await clear_emergency_stop()
    return {
        "emergency_stop": False,
        "message": "Emergency stop cleared; live trading still requires an explicit engine start",
    }
