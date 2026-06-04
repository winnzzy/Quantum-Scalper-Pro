"""Strategy API routes."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.auth.service import get_current_active_user
from app.models.user import User
from app.strategies.registry import StrategyRegistry

router = APIRouter()


@router.get("/list")
async def list_strategies(current_user: User = Depends(get_current_active_user)):
    """List available strategies."""
    strategies = StrategyRegistry.list_strategies()
    return {"strategies": strategies}


@router.get("/{strategy_name}/info")
async def get_strategy_info(
    strategy_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get strategy information."""
    info = StrategyRegistry.get_strategy_info(strategy_name)
    return info
