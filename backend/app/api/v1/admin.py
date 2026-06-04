"""Admin API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.auth.service import get_admin_user
from app.models.user import User, UserRole, SubscriptionPlan
from app.models.system import SystemHealth, AuditLog
from app.models.trading import Trade

router = APIRouter()


@router.get("/dashboard")
async def admin_dashboard(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin dashboard stats."""
    # User counts
    total_users = await db.execute(select(func.count(User.id)))
    active_users = await db.execute(select(func.count(User.id)).where(User.is_active == True))

    # Trade counts
    total_trades = await db.execute(select(func.count(Trade.id)))

    # Recent activity
    recent_logs = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20)
    )

    return {
        "total_users": total_users.scalar(),
        "active_users": active_users.scalar(),
        "total_trades": total_trades.scalar(),
        "recent_activity": recent_logs.scalars().all()
    }


@router.get("/users")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users."""
    result = await db.execute(select(User).offset(skip).limit(limit))
    return result.scalars().all()


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    role: UserRole,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user role."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role
    await db.commit()
    return user


@router.get("/system/health")
async def system_health(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get system health."""
    result = await db.execute(
        select(SystemHealth).order_by(SystemHealth.created_at.desc()).limit(1)
    )
    health = result.scalar_one_or_none()

    if not health:
        return {"status": "unknown", "message": "No health data available"}

    return health
