"""Evidence-based gates for the private owner's live launch."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.evidence import qualification_readiness
from app.core.config import settings
from app.core.markets import MARKETS, normalize_symbol
from app.models.trading import BrokerType, Trade, TradeStatus


async def paper_burn_in_readiness(
    db: AsyncSession, user_id: int, symbols: list[str] | None = None
) -> dict:
    symbols = [normalize_symbol(s) for s in (symbols or list(MARKETS))]
    markets = []
    blockers = []
    for symbol in symbols:
        row = (
            await db.execute(
                select(
                    func.count(Trade.id),
                    func.min(Trade.entry_time),
                    func.max(Trade.exit_time),
                ).where(
                    Trade.user_id == user_id,
                    Trade.symbol == symbol,
                    Trade.broker == BrokerType.PAPER,
                    Trade.status == TradeStatus.CLOSED,
                )
            )
        ).one()
        count, first_entry, last_exit = row
        elapsed_days = 0.0
        if first_entry and last_exit:
            if first_entry.tzinfo is None:
                first_entry = first_entry.replace(tzinfo=timezone.utc)
            if last_exit.tzinfo is None:
                last_exit = last_exit.replace(tzinfo=timezone.utc)
            elapsed_days = max(0.0, (last_exit - first_entry).total_seconds() / 86400)
        market_blockers = []
        if count < settings.MIN_PAPER_TRADES_PER_MARKET:
            market_blockers.append(
                f"{count}/{settings.MIN_PAPER_TRADES_PER_MARKET} closed paper trades"
            )
        if elapsed_days < settings.MIN_PAPER_BURN_IN_DAYS:
            market_blockers.append(
                f"{elapsed_days:.1f}/{settings.MIN_PAPER_BURN_IN_DAYS} paper burn-in days"
            )
        blockers.extend(f"{symbol}: {item}" for item in market_blockers)
        markets.append(
            {
                "symbol": symbol,
                "closed_trades": count,
                "elapsed_days": round(elapsed_days, 1),
                "ready": not market_blockers,
            }
        )
    return {"ready": not blockers, "markets": markets, "blockers": blockers}


async def private_launch_readiness(db: AsyncSession, user_id: int) -> dict:
    paper = await paper_burn_in_readiness(db, user_id)
    qualifications = []
    blockers = list(paper["blockers"])
    for symbol, profile in MARKETS.items():
        qualification = qualification_readiness(symbol, profile.default_timeframe)
        qualifications.append(qualification)
        blockers.extend(f"{symbol}: {item}" for item in qualification["blockers"])
    controls = {
        "private_mode": settings.PRIVATE_MODE,
        "owner_configured": bool(settings.OWNER_EMAIL),
        "live_trading_armed": settings.LIVE_TRADING_ENABLED,
        "emergency_stop_clear": not settings.EMERGENCY_STOP,
    }
    if not controls["private_mode"]:
        blockers.append("PRIVATE_MODE must be enabled")
    if not controls["owner_configured"]:
        blockers.append("OWNER_EMAIL is not configured")
    if not controls["live_trading_armed"]:
        blockers.append("LIVE_TRADING_ENABLED is false")
    if not controls["emergency_stop_clear"]:
        blockers.append("EMERGENCY_STOP is active")
    return {
        "ready_for_live": not blockers,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "controls": controls,
        "paper_burn_in": paper,
        "qualifications": qualifications,
        "blockers": blockers,
    }
