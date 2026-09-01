"""Authenticated backtesting and validation routes."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.auth.service import get_current_active_user
from app.backtesting.engine import backtest_engine
from app.models.user import User
from app.strategies.registry import StrategyRegistry


router = APIRouter()


class WalkForwardRequest(BaseModel):
    """Bounded input for chronological strategy validation."""

    strategy_name: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=3, max_length=30)
    timeframe: Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"] = "1m"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    initial_balance: float = Field(default=100000.0, gt=0, le=1000000000)
    parameter_candidates: List[Dict[str, Any]] = Field(
        default_factory=lambda: [{}], min_length=1, max_length=20
    )
    train_candles: int = Field(default=1000, ge=60, le=500000)
    test_candles: int = Field(default=250, ge=60, le=100000)
    step_candles: Optional[int] = Field(default=None, ge=1, le=100000)
    min_train_trades: int = Field(default=5, ge=1, le=10000)
    risk_per_trade_pct: Optional[float] = Field(default=None, gt=0, le=5)
    max_drawdown_pct: Optional[float] = Field(default=None, gt=0, le=100)
    max_consecutive_losses: Optional[int] = Field(default=None, ge=1, le=100)
    spread_pct: Optional[float] = Field(default=None, ge=0, le=0.05)
    commission_rate: Optional[float] = Field(default=None, ge=0, le=0.05)
    slippage_rate: Optional[float] = Field(default=None, ge=0, le=0.05)

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError("start_date must be earlier than end_date")
        return self


@router.post("/walk-forward")
async def run_walk_forward(
    request: WalkForwardRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Run bounded rolling out-of-sample strategy validation."""
    if request.strategy_name not in StrategyRegistry.list_strategies():
        raise HTTPException(status_code=404, detail="Strategy not found")

    result = await backtest_engine.run_walk_forward(**request.model_dump())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
