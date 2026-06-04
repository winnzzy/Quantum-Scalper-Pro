"""Admin System - User and system management.

Features:
- User management
- System monitoring
- License management
- Audit logs
- Performance metrics
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.user import User, UserRole, SubscriptionPlan
from app.models.system import SystemHealth, AuditLog
from app.models.trading import Trade
from app.models.licensing import License


class AdminSystem:
    """Admin management system."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get admin dashboard statistics."""
        # User counts
        total_users_result = await self.db.execute(select(func.count(User.id)))
        total_users = total_users_result.scalar() or 0

        active_users_result = await self.db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        active_users = active_users_result.scalar() or 0

        # Trade counts
        total_trades_result = await self.db.execute(select(func.count(Trade.id)))
        total_trades = total_trades_result.scalar() or 0

        # Recent trades
        recent_trades_result = await self.db.execute(
            select(Trade).order_by(desc(Trade.created_at)).limit(10)
        )
        recent_trades = recent_trades_result.scalars().all()

        # License stats
        license_result = await self.db.execute(
            select(func.count(License.id)).where(License.status == "active")
        )
        active_licenses = license_result.scalar() or 0

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_trades": total_trades,
            "active_licenses": active_licenses,
            "recent_trades": recent_trades,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def get_users(
        self,
        skip: int = 0,
        limit: int = 100,
        role: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[User]:
        """Get users with filters."""
        query = select(User)

        if role:
            query = query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        query = query.offset(skip).limit(limit).order_by(desc(User.created_at))
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_user_status(self, user_id: int, is_active: bool) -> bool:
        """Activate or deactivate user."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return False

        user.is_active = is_active
        await self.db.commit()

        logger.info(f"User {user_id} status updated to {is_active}")
        return True

    async def update_user_role(self, user_id: int, role: UserRole) -> bool:
        """Update user role."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return False

        user.role = role
        await self.db.commit()

        logger.info(f"User {user_id} role updated to {role.value}")
        return True

    async def get_audit_logs(
        self,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get audit logs."""
        query = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)

        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_system_health(self) -> Optional[SystemHealth]:
        """Get latest system health."""
        result = await self.db.execute(
            select(SystemHealth).order_by(desc(SystemHealth.created_at)).limit(1)
        )
        return result.scalar_one_or_none()

    async def generate_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate system report."""
        # Trade statistics
        trades_result = await self.db.execute(
            select(func.count(Trade.id)).where(
                and_(Trade.created_at >= start_date, Trade.created_at <= end_date)
            )
        )
        total_trades = trades_result.scalar() or 0

        # P&L
        pnl_result = await self.db.execute(
            select(func.sum(Trade.net_pnl)).where(
                and_(Trade.created_at >= start_date, Trade.created_at <= end_date)
            )
        )
        total_pnl = pnl_result.scalar() or 0

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_trades": total_trades,
            "total_pnl": float(total_pnl),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
