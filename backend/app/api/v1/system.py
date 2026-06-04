"""System API routes."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.models.user import User
from app.models.system import Notification
from sqlalchemy import select, desc

router = APIRouter()


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
