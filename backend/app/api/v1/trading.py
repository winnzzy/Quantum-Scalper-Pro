"""Trading API routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.models.user import User
from app.models.trading import Trade, TradeStatus, Position, Order, StrategyConfig
from app.engines.trading import trading_engine_manager
from app.brokers.factory import BrokerFactory

router = APIRouter()


class TradeCreate(BaseModel):
    symbol: str
    direction: str  # buy or sell
    quantity: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    order_type: str = "market"
    broker_type: str = "paper"


class StrategyConfigCreate(BaseModel):
    name: str
    strategy_type: str
    parameters: dict = {}
    symbols: list = []
    timeframes: list = []
    risk_per_trade: float | None = None
    is_active: bool = True


@router.get("/trades")
async def get_trades(
    status: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user trades."""
    query = select(Trade).where(Trade.user_id == current_user.id)

    if status:
        query = query.where(Trade.status == status)

    query = query.order_by(desc(Trade.created_at)).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()

    return trades


@router.get("/trades/{trade_id}")
async def get_trade(
    trade_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get trade details."""
    result = await db.execute(
        select(Trade).where(Trade.id == trade_id, Trade.user_id == current_user.id)
    )
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    return trade


@router.post("/trades")
async def create_trade(
    trade_data: TradeCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Manually create a trade."""
    from app.engines.execution import ExecutionEngine
    from app.strategies.base import Signal, SignalType

    execution = ExecutionEngine(db, current_user.id)

    signal = Signal(
        type=SignalType.BUY if trade_data.direction == "buy" else SignalType.SELL,
        symbol=trade_data.symbol,
        timestamp=datetime.now(timezone.utc),
        price=Decimal(str(trade_data.price)) if trade_data.price else Decimal("0"),
        stop_loss=Decimal(str(trade_data.stop_loss)) if trade_data.stop_loss else None,
        take_profit=Decimal(str(trade_data.take_profit)) if trade_data.take_profit else None,
        confidence=0.5
    )

    result = await execution.execute_signal(
        signal,
        trade_data.broker_type,
        {
            "strategy_type": "manual",
            "manual": True,
            "use_ai_filter": False,
            "use_news_filter": True,
        }
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/trades/{trade_id}/close")
async def close_trade(
    trade_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Close a trade."""
    from app.engines.execution import ExecutionEngine

    execution = ExecutionEngine(db, current_user.id)
    result = await execution.close_trade(trade_id)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.get("/positions")
async def get_positions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get open positions."""
    result = await db.execute(
        select(Position).where(
            and_(Position.user_id == current_user.id, Position.is_open == True)
        )
    )
    return result.scalars().all()


@router.get("/account")
async def get_account(
    broker_type: str = "paper",
    current_user: User = Depends(get_current_active_user)
):
    """Get account info from broker."""
    broker = await BrokerFactory.get_broker(broker_type, current_user.id)
    account = await broker.get_account_info()

    return {
        "balance": float(account.balance),
        "equity": float(account.equity),
        "margin_used": float(account.margin_used),
        "margin_free": float(account.margin_free),
        "currency": account.currency,
        "open_positions": account.open_positions
    }


@router.get("/market/{symbol}")
async def get_market_data(
    symbol: str,
    broker_type: str = "paper",
    current_user: User = Depends(get_current_active_user)
):
    """Get market data for symbol."""
    broker = await BrokerFactory.get_broker(broker_type, current_user.id)
    data = await broker.get_market_data(symbol)

    return {
        "symbol": data.symbol,
        "bid": float(data.bid),
        "ask": float(data.ask),
        "last": float(data.last),
        "spread": float(data.ask - data.bid),
        "volume_24h": float(data.volume_24h) if data.volume_24h else None,
        "timestamp": data.timestamp.isoformat() if data.timestamp else None
    }


@router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    timeframe: str = "1m",
    limit: int = 100,
    broker_type: str = "paper",
    current_user: User = Depends(get_current_active_user)
):
    """Get OHLCV data."""
    broker = await BrokerFactory.get_broker(broker_type, current_user.id)
    data = await broker.get_ohlcv(symbol, timeframe, limit)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "data": data
    }


@router.get("/strategies/configs")
async def get_strategy_configs(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get strategy configurations."""
    result = await db.execute(
        select(StrategyConfig).where(StrategyConfig.user_id == current_user.id)
    )
    return result.scalars().all()


@router.post("/strategies/configs")
async def create_strategy_config(
    config: StrategyConfigCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create strategy configuration."""
    strategy_config = StrategyConfig(
        user_id=current_user.id,
        name=config.name,
        strategy_type=config.strategy_type,
        parameters=config.parameters,
        symbols=config.symbols,
        timeframes=config.timeframes,
        risk_per_trade=Decimal(str(config.risk_per_trade)) if config.risk_per_trade else None,
        is_active=config.is_active
    )

    db.add(strategy_config)
    await db.commit()
    await db.refresh(strategy_config)

    return strategy_config


@router.post("/start")
async def start_trading(
    strategy_config_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Start trading engine."""
    result = await db.execute(
        select(StrategyConfig).where(
            and_(StrategyConfig.id == strategy_config_id, StrategyConfig.user_id == current_user.id)
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Strategy config not found")

    # Convert the persisted configuration into the runtime contract.
    config_dict = {
        "strategy_type": config.strategy_type,
        "symbols": config.symbols,
        "timeframes": config.timeframes,
        "parameters": config.parameters,
        "broker_type": current_user.default_broker or "paper",
        "is_active": config.is_active,
        "risk_per_trade": float(config.risk_per_trade) if config.risk_per_trade else None,
        "use_ai_filter": config.use_ai_filter,
        "use_news_filter": config.use_news_filter
    }

    try:
        runtime_status = await trading_engine_manager.start(current_user.id, [config_dict])
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"message": "Trading engine started", "status": runtime_status}


@router.post("/stop")
async def stop_trading(
    current_user: User = Depends(get_current_active_user),
):
    """Stop trading engine."""
    runtime_status = await trading_engine_manager.stop(current_user.id)
    return {"message": "Trading engine stopped", "status": runtime_status}


@router.get("/status")
async def get_trading_status(
    current_user: User = Depends(get_current_active_user),
):
    """Get trading engine status."""
    return await trading_engine_manager.status(current_user.id)
