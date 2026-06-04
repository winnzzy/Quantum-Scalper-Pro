"""Usage Analytics Service.

Tracks and reports on:
- Daily usage records (trades, backtests, API calls)
- P&L tracking per user
- Feature usage tracking
- Plan utilization metrics
- Conversion funnel analytics
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal

from sqlalchemy import select, func, and_, desc, text

from app.core.database import async_session
from app.core.logging import logger
from app.core.redis import redis_client
from app.models.subscription import (
    UsageRecord, CustomerSubscription, SubscriptionStatus,
    SubscriptionPlanConfig, PlanTier, Payment, PaymentStatus,
)
from app.models.user import User


class AnalyticsService:
    """Usage analytics and reporting."""

    # ──────────────────────────────────────────────────────────────────
    # Usage Tracking
    # ──────────────────────────────────────────────────────────────────

    async def record_usage(
        self,
        user_id: int,
        trades_executed: int = 0,
        backtests_run: int = 0,
        api_calls: int = 0,
        signals_generated: int = 0,
        strategies_active: int = 0,
        total_pnl: Decimal = Decimal("0"),
        win_rate: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
        usage_date: Optional[datetime] = None,
    ):
        """Record or update daily usage for a user."""
        date = usage_date or datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        async with async_session() as session:
            # Check if record exists for this date
            result = await session.execute(
                select(UsageRecord).where(
                    UsageRecord.user_id == user_id,
                    UsageRecord.usage_date == date,
                )
            )
            record = result.scalar_one_or_none()

            if record:
                # Update existing record (accumulate)
                record.trades_executed += trades_executed
                record.backtests_run += backtests_run
                record.api_calls += api_calls
                record.signals_generated += signals_generated
                record.strategies_active = strategies_active
                record.total_pnl += total_pnl
                if win_rate is not None:
                    record.win_rate = win_rate
                if max_drawdown is not None:
                    record.max_drawdown = max_drawdown
                if sharpe_ratio is not None:
                    record.sharpe_ratio = sharpe_ratio
            else:
                record = UsageRecord(
                    user_id=user_id,
                    usage_date=date,
                    trades_executed=trades_executed,
                    backtests_run=backtests_run,
                    api_calls=api_calls,
                    signals_generated=signals_generated,
                    strategies_active=strategies_active,
                    total_pnl=total_pnl,
                    win_rate=win_rate,
                    max_drawdown=max_drawdown,
                    sharpe_ratio=sharpe_ratio,
                )
                session.add(record)

            await session.commit()

    async def increment_api_call(self, user_id: int):
        """Lightweight API call counter (Redis-first, periodic DB flush)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"usage:{user_id}:{today}:api_calls"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 86400 * 2)
        return count

    async def increment_trades(self, user_id: int, count: int = 1):
        """Increment trade counter."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"usage:{user_id}:{today}:trades"
        total = await redis_client.incrby(key, count)
        if total == count:
            await redis_client.expire(key, 86400 * 2)
        return total

    async def get_today_usage(self, user_id: int) -> Dict[str, int]:
        """Get today's usage from Redis (fast path)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        keys = ["api_calls", "trades", "backtests"]
        result = {}
        for k in keys:
            val = await redis_client.get(f"usage:{user_id}:{today}:{k}")
            result[k] = int(val) if val else 0
        return result

    # ──────────────────────────────────────────────────────────────────
    # User Analytics
    # ──────────────────────────────────────────────────────────────────

    async def get_user_analytics(
        self,
        user_id: int,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get analytics summary for a user."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        async with async_session() as session:
            result = await session.execute(
                select(UsageRecord)
                .where(
                    UsageRecord.user_id == user_id,
                    UsageRecord.usage_date >= since,
                )
                .order_by(UsageRecord.usage_date)
            )
            records = result.scalars().all()

            if not records:
                return {
                    "period_days": days,
                    "total_trades": 0,
                    "total_backtests": 0,
                    "total_api_calls": 0,
                    "total_signals": 0,
                    "total_pnl": 0,
                    "avg_win_rate": None,
                    "max_drawdown": None,
                    "avg_sharpe": None,
                    "daily_breakdown": [],
                }

            total_trades = sum(r.trades_executed for r in records)
            total_backtests = sum(r.backtests_run for r in records)
            total_api_calls = sum(r.api_calls for r in records)
            total_signals = sum(r.signals_generated for r in records)
            total_pnl = sum(float(r.total_pnl or 0) for r in records)

            win_rates = [r.win_rate for r in records if r.win_rate is not None]
            drawdowns = [r.max_drawdown for r in records if r.max_drawdown is not None]
            sharpes = [r.sharpe_ratio for r in records if r.sharpe_ratio is not None]

            daily_breakdown = [
                {
                    "date": r.usage_date.strftime("%Y-%m-%d"),
                    "trades": r.trades_executed,
                    "backtests": r.backtests_run,
                    "api_calls": r.api_calls,
                    "pnl": float(r.total_pnl or 0),
                    "win_rate": r.win_rate,
                }
                for r in records
            ]

            return {
                "period_days": days,
                "total_trades": total_trades,
                "total_backtests": total_backtests,
                "total_api_calls": total_api_calls,
                "total_signals": total_signals,
                "total_pnl": round(total_pnl, 2),
                "avg_win_rate": round(sum(win_rates) / len(win_rates), 2) if win_rates else None,
                "max_drawdown": max(drawdowns) if drawdowns else None,
                "avg_sharpe": round(sum(sharpes) / len(sharpes), 2) if sharpes else None,
                "daily_breakdown": daily_breakdown,
            }

    # ──────────────────────────────────────────────────────────────────
    # Platform Analytics
    # ──────────────────────────────────────────────────────────────────

    async def get_platform_analytics(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get platform-wide analytics."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        async with async_session() as session:
            # Total usage
            usage_result = await session.execute(
                select(
                    func.sum(UsageRecord.trades_executed),
                    func.sum(UsageRecord.backtests_run),
                    func.sum(UsageRecord.api_calls),
                    func.sum(UsageRecord.signals_generated),
                    func.sum(UsageRecord.total_pnl),
                    func.count(func.distinct(UsageRecord.user_id)),
                ).where(UsageRecord.usage_date >= since)
            )
            row = usage_result.first()

            # Active users (users with any usage in period)
            active_users = int(row[5] or 0) if row else 0

            # Plan utilization
            plan_util = await session.execute(
                select(
                    SubscriptionPlanConfig.plan_tier,
                    func.count(CustomerSubscription.id),
                    func.avg(CustomerSubscription.price_snapshot),
                )
                .join(SubscriptionPlanConfig, CustomerSubscription.plan_id == SubscriptionPlanConfig.id)
                .where(CustomerSubscription.status == SubscriptionStatus.ACTIVE)
                .group_by(SubscriptionPlanConfig.plan_tier)
            )
            plan_utilization = {
                r[0].value: {"count": r[1], "avg_price": float(r[2] or 0)}
                for r in plan_util.fetchall()
            }

            # Conversion funnel
            total_users = await session.execute(select(func.count(User.id)))
            total = total_users.scalar() or 0

            trial_users = await session.execute(
                select(func.count(CustomerSubscription.id)).where(
                    CustomerSubscription.status == SubscriptionStatus.TRIALING
                )
            )
            trials = trial_users.scalar() or 0

            paid_users = await session.execute(
                select(func.count(CustomerSubscription.id)).where(
                    CustomerSubscription.status == SubscriptionStatus.ACTIVE
                )
            )
            paid = paid_users.scalar() or 0

            # Revenue by period
            revenue_7d = await session.execute(
                select(func.sum(Payment.amount)).where(
                    Payment.status == PaymentStatus.SUCCEEDED,
                    Payment.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
                )
            )
            revenue_30d = await session.execute(
                select(func.sum(Payment.amount)).where(
                    Payment.status == PaymentStatus.SUCCEEDED,
                    Payment.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
                )
            )

            return {
                "period_days": days,
                "active_users": active_users,
                "total_users": total,
                "usage": {
                    "total_trades": int(row[0] or 0) if row else 0,
                    "total_backtests": int(row[1] or 0) if row else 0,
                    "total_api_calls": int(row[2] or 0) if row else 0,
                    "total_signals": int(row[3] or 0) if row else 0,
                    "total_pnl": float(row[4] or 0) if row else 0,
                },
                "plan_utilization": plan_utilization,
                "conversion_funnel": {
                    "total_users": total,
                    "trial_users": trials,
                    "paid_users": paid,
                    "trial_conversion_rate": round(paid / max(trials, 1) * 100, 1),
                    "paid_rate": round(paid / max(total, 1) * 100, 1),
                },
                "revenue": {
                    "last_7_days": float(revenue_7d.scalar() or 0),
                    "last_30_days": float(revenue_30d.scalar() or 0),
                },
            }

    # ──────────────────────────────────────────────────────────────────
    # Flush Redis Counters to DB
    # ──────────────────────────────────────────────────────────────────

    async def flush_daily_usage(self):
        """Flush Redis usage counters to database.

        Should be called periodically (e.g., every hour or at end of day).
        """
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        # Scan for usage keys from yesterday
        pattern = f"usage:*:{yesterday}:*"
        cursor = 0
        flushed = 0

        while True:
            cursor, keys = await redis_client._client.scan(
                cursor=cursor, match=pattern, count=100
            )
            for key in keys:
                parts = key.split(":")
                if len(parts) >= 4:
                    user_id = int(parts[1])
                    metric = parts[3]
                    value = await redis_client.get(key)
                    if value and int(value) > 0:
                        date = datetime.strptime(yesterday, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        await self.record_usage(
                            user_id=user_id,
                            usage_date=date,
                            **{metric if metric != "api_calls" else "api_calls": int(value)}
                        )
                        flushed += 1

            if cursor == 0:
                break

        logger.info(f"Flushed {flushed} usage records to database")
        return flushed


# Global instance
analytics_service = AnalyticsService()