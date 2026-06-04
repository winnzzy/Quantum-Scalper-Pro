"""Analytics API routes."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.models.user import User
from app.models.trading import Trade, TradeStatus
from app.models.analytics import PerformanceReport, TradeJournal

router = APIRouter()


@router.get("/performance")
async def get_performance(
    period: str = "daily",  # daily, weekly, monthly
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get performance metrics."""
    now = datetime.now(timezone.utc)

    if period == "daily":
        start = now - timedelta(days=1)
    elif period == "weekly":
        start = now - timedelta(weeks=1)
    elif period == "monthly":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=1)

    # Get trades in period
    result = await db.execute(
        select(Trade).where(
            and_(
                Trade.user_id == current_user.id,
                Trade.status == TradeStatus.CLOSED,
                Trade.exit_time >= start
            )
        )
    )
    trades = result.scalars().all()

    if not trades:
        return {
            "period": period,
            "total_trades": 0,
            "win_rate": 0,
            "net_pnl": 0,
            "profit_factor": 0
        }

    total_trades = len(trades)
    winning_trades = len([t for t in trades if t.net_pnl and float(t.net_pnl) > 0])
    losing_trades = total_trades - winning_trades

    gross_profit = sum(float(t.net_pnl) for t in trades if t.net_pnl and float(t.net_pnl) > 0)
    gross_loss = abs(sum(float(t.net_pnl) for t in trades if t.net_pnl and float(t.net_pnl) < 0))
    net_pnl = gross_profit - gross_loss

    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    return {
        "period": period,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": round(win_rate, 2),
        "gross_profit": round(gross_profit, 8),
        "gross_loss": round(gross_loss, 8),
        "net_pnl": round(net_pnl, 8),
        "profit_factor": round(profit_factor, 4),
        "avg_win": round(gross_profit / winning_trades, 8) if winning_trades > 0 else 0,
        "avg_loss": round(gross_loss / losing_trades, 8) if losing_trades > 0 else 0
    }


@router.get("/trades/distribution")
async def get_trade_distribution(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get trade distribution by symbol and strategy."""
    result = await db.execute(
        select(
            Trade.symbol,
            Trade.strategy_name,
            func.count(Trade.id).label("count"),
            func.sum(Trade.net_pnl).label("total_pnl")
        )
        .where(
            and_(Trade.user_id == current_user.id, Trade.status == TradeStatus.CLOSED)
        )
        .group_by(Trade.symbol, Trade.strategy_name)
    )

    rows = result.all()
    return [
        {
            "symbol": row.symbol,
            "strategy": row.strategy_name,
            "trades": row.count,
            "pnl": float(row.total_pnl) if row.total_pnl else 0
        }
        for row in rows
    ]
