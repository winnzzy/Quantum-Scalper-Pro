"""Pydantic schemas for API validation."""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any


class UserBase(BaseModel):
    email: EmailStr
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    id: int
    role: str
    is_active: bool
    subscription_plan: str
    created_at: datetime

    class Config:
        from_attributes = True


class TradeBase(BaseModel):
    symbol: str
    direction: str
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


class TradeResponse(TradeBase):
    id: int
    status: str
    entry_price: Optional[Decimal]
    exit_price: Optional[Decimal]
    net_pnl: Optional[Decimal]
    strategy_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class StrategyConfigBase(BaseModel):
    name: str
    strategy_type: str
    parameters: Dict[str, Any] = {}
    symbols: List[str] = []
    timeframes: List[str] = []
    is_active: bool = True


class StrategyConfigResponse(StrategyConfigBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RiskProfileBase(BaseModel):
    risk_per_trade_percent: float = 0.5
    daily_loss_limit_percent: float = 3.0
    weekly_loss_limit_percent: float = 5.0
    monthly_loss_limit_percent: float = 10.0
    max_drawdown_percent: float = 15.0
    max_consecutive_losses: int = 5
    max_open_trades: int = 10
    mandatory_stop_loss: bool = True


class RiskProfileResponse(RiskProfileBase):
    id: int
    user_id: int
    trading_paused: bool
    pause_reason: Optional[str]
    current_daily_loss: Decimal
    current_drawdown: Decimal
    consecutive_losses: int

    class Config:
        from_attributes = True


class PerformanceMetrics(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    net_pnl: float
    profit_factor: float
    sharpe_ratio: Optional[float] = None
    max_drawdown: float


class NotificationBase(BaseModel):
    type: str
    title: str
    message: str
    priority: str = "normal"


class NotificationResponse(NotificationBase):
    id: int
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LicenseBase(BaseModel):
    license_key: str
    plan: str
    status: str


class LicenseResponse(LicenseBase):
    id: int
    activated_at: Optional[datetime]
    expires_at: Optional[datetime]
    max_accounts: int
    max_strategies: int

    class Config:
        from_attributes = True
