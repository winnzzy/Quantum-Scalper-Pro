"""Risk Management Engine - Highest Priority Module."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger, trade_logger
from app.models.risk import RiskProfile, RiskEvent, RiskEventType
from app.models.trading import Trade, TradeStatus, TradeDirection
from app.models.user import User
from app.core.redis import redis_client


class RiskManagementEngine:
    """
    Risk Management Engine - Capital Preservation Priority.

    Implements:
    - Maximum risk per trade (0.25%, 0.5%, 1%, Custom)
    - Daily/Weekly/Monthly loss limits
    - Maximum drawdown protection
    - Consecutive loss protection
    - Spread protection
    - Volatility protection
    - Weekend protection
    - Maximum open trades
    - Position sizing
    - Mandatory stop loss
    - Mandatory risk validation
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_trade(
        self,
        user_id: int,
        symbol: str,
        direction: str,
        quantity: Decimal,
        price: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        risk_percent: Optional[Decimal] = None,
        broker_type: str = "paper"
    ) -> Dict[str, Any]:
        """
        Validate trade against all risk rules.

        Returns:
            {
                "allowed": bool,
                "reason": str,
                "risk_amount": Decimal,
                "position_size": Decimal,
                "adjusted_stop_loss": Optional[Decimal],
                "warnings": List[str]
            }
        """
        result = {
            "allowed": True,
            "reason": "",
            "risk_amount": Decimal("0"),
            "position_size": quantity,
            "adjusted_stop_loss": stop_loss,
            "warnings": []
        }

        # Get risk profile
        risk_profile = await self._get_risk_profile(user_id)
        if not risk_profile:
            result["allowed"] = False
            result["reason"] = "Risk profile not found"
            return result

        # Check if trading is paused
        if risk_profile.trading_paused:
            result["allowed"] = False
            result["reason"] = f"Trading paused: {risk_profile.pause_reason}"
            await self._log_risk_event(user_id, RiskEventType.MANUAL_PAUSE, result["reason"], symbol)
            return result

        # 1. Mandatory stop loss check
        if risk_profile.mandatory_stop_loss and stop_loss is None:
            result["allowed"] = False
            result["reason"] = "Stop loss is mandatory"
            return result

        # 2. Check loss limits
        loss_check = await self._check_loss_limits(user_id, risk_profile)
        if not loss_check["allowed"]:
            result["allowed"] = False
            result["reason"] = loss_check["reason"]
            await self._log_risk_event(user_id, loss_check["event_type"], loss_check["reason"], symbol)
            return result

        # 3. Check drawdown
        drawdown_check = await self._check_drawdown(user_id, risk_profile)
        if not drawdown_check["allowed"]:
            result["allowed"] = False
            result["reason"] = drawdown_check["reason"]
            await self._log_risk_event(user_id, RiskEventType.MAX_DRAWDOWN, drawdown_check["reason"], symbol)
            return result

        # 4. Check consecutive losses
        consecutive_check = await self._check_consecutive_losses(user_id, risk_profile)
        if not consecutive_check["allowed"]:
            result["allowed"] = False
            result["reason"] = consecutive_check["reason"]
            await self._log_risk_event(user_id, RiskEventType.CONSECUTIVE_LOSSES, consecutive_check["reason"], symbol)
            return result

        # 5. Check max open trades
        open_trades_check = await self._check_open_trades(user_id, risk_profile, symbol)
        if not open_trades_check["allowed"]:
            result["allowed"] = False
            result["reason"] = open_trades_check["reason"]
            return result

        # 6. Weekend protection
        weekend_check = self._check_weekend_protection(risk_profile)
        if not weekend_check["allowed"]:
            result["allowed"] = False
            result["reason"] = weekend_check["reason"]
            await self._log_risk_event(user_id, RiskEventType.WEEKEND_PROTECTION, weekend_check["reason"], symbol)
            return result

        # 7. Calculate position size and risk
        sizing = await self._calculate_position_size(
            user_id, symbol, price, stop_loss, risk_percent, risk_profile, direction
        )

        result["risk_amount"] = sizing["risk_amount"]
        result["position_size"] = sizing["position_size"]
        result["adjusted_stop_loss"] = sizing["adjusted_stop_loss"]

        if sizing["warning"]:
            result["warnings"].append(sizing["warning"])

        # 8. Validate risk per trade
        account_balance = await self._get_account_balance(user_id)
        if account_balance > 0:
            actual_risk_pct = (result["risk_amount"] / account_balance) * 100
            max_risk = risk_profile.risk_per_trade_custom or risk_profile.risk_per_trade_percent

            if actual_risk_pct > float(max_risk) * Decimal("1.01"):  # 1% tolerance
                result["allowed"] = False
                result["reason"] = f"Risk per trade ({actual_risk_pct:.2f}%) exceeds maximum ({max_risk}%)"
                return result

        trade_logger.info(
            f"RISK VALIDATED: User {user_id} | {symbol} {direction} | "
            f"Risk: {result['risk_amount']} | Size: {result['position_size']}"
        )

        return result

    async def _get_risk_profile(self, user_id: int) -> Optional[RiskProfile]:
        """Get or create risk profile."""
        result = await self.db.execute(
            select(RiskProfile).where(RiskProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            # Create default profile
            profile = RiskProfile(user_id=user_id)
            self.db.add(profile)
            await self.db.commit()
            await self.db.refresh(profile)

        return profile

    async def _check_loss_limits(self, user_id: int, profile: RiskProfile) -> Dict[str, Any]:
        """Check daily/weekly/monthly loss limits."""
        now = datetime.now(timezone.utc)

        # Daily check
        if float(profile.current_daily_loss) > 0 and            abs(float(profile.current_daily_loss)) >= float(profile.daily_loss_limit_percent):
            return {
                "allowed": False,
                "reason": f"Daily loss limit reached: {profile.current_daily_loss}%",
                "event_type": RiskEventType.DAILY_LOSS_LIMIT
            }

        # Weekly check
        if float(profile.current_weekly_loss) > 0 and            abs(float(profile.current_weekly_loss)) >= float(profile.weekly_loss_limit_percent):
            return {
                "allowed": False,
                "reason": f"Weekly loss limit reached: {profile.current_weekly_loss}%",
                "event_type": RiskEventType.WEEKLY_LOSS_LIMIT
            }

        # Monthly check
        if float(profile.current_monthly_loss) > 0 and            abs(float(profile.current_monthly_loss)) >= float(profile.monthly_loss_limit_percent):
            return {
                "allowed": False,
                "reason": f"Monthly loss limit reached: {profile.current_monthly_loss}%",
                "event_type": RiskEventType.MONTHLY_LOSS_LIMIT
            }

        return {"allowed": True}

    async def _check_drawdown(self, user_id: int, profile: RiskProfile) -> Dict[str, Any]:
        """Check maximum drawdown."""
        if float(profile.current_drawdown) >= float(profile.max_drawdown_percent):
            # Auto-pause trading
            profile.trading_paused = True
            profile.pause_reason = f"Max drawdown reached: {profile.current_drawdown}%"
            profile.paused_at = datetime.now(timezone.utc)
            await self.db.commit()

            return {
                "allowed": False,
                "reason": profile.pause_reason
            }

        return {"allowed": True}

    async def _check_consecutive_losses(self, user_id: int, profile: RiskProfile) -> Dict[str, Any]:
        """Check consecutive losses."""
        if profile.consecutive_losses >= profile.max_consecutive_losses:
            return {
                "allowed": False,
                "reason": f"Max consecutive losses reached: {profile.consecutive_losses}"
            }

        return {"allowed": True}

    async def _check_open_trades(self, user_id: int, profile: RiskProfile, symbol: str) -> Dict[str, Any]:
        """Check maximum open trades."""
        result = await self.db.execute(
            select(func.count(Trade.id))
            .where(
                and_(
                    Trade.user_id == user_id,
                    Trade.status == TradeStatus.OPEN
                )
            )
        )
        open_count = result.scalar() or 0

        if open_count >= profile.max_open_trades:
            return {
                "allowed": False,
                "reason": f"Max open trades reached: {open_count}/{profile.max_open_trades}"
            }

        # Check symbol-specific limit (max 2 per symbol)
        result = await self.db.execute(
            select(func.count(Trade.id))
            .where(
                and_(
                    Trade.user_id == user_id,
                    Trade.status == TradeStatus.OPEN,
                    Trade.symbol == symbol
                )
            )
        )
        symbol_count = result.scalar() or 0
        if symbol_count >= 2:
            return {
                "allowed": False,
                "reason": f"Max trades for {symbol} reached: 2"
            }

        return {"allowed": True}

    def _check_weekend_protection(self, profile: RiskProfile) -> Dict[str, Any]:
        """Check weekend trading protection."""
        if not profile.weekend_protection_enabled:
            return {"allowed": True}

        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        hour = now.hour

        # Friday after 22:00 UTC to Sunday 22:00 UTC
        if weekday == 4 and hour >= 22:  # Friday evening
            return {"allowed": False, "reason": "Weekend protection: Friday after 22:00 UTC"}
        elif weekday in [5, 6]:  # Saturday, Sunday
            return {"allowed": False, "reason": "Weekend protection: Weekend trading disabled"}
        elif weekday == 0 and hour < 22:  # Sunday before 22:00 UTC
            return {"allowed": False, "reason": "Weekend protection: Sunday before 22:00 UTC"}

        return {"allowed": True}

    async def _calculate_position_size(
        self,
        user_id: int,
        symbol: str,
        price: Decimal,
        stop_loss: Optional[Decimal],
        risk_percent: Optional[Decimal],
        profile: RiskProfile,
        direction: str
    ) -> Dict[str, Any]:
        """Calculate position size based on risk parameters."""
        account_balance = await self._get_account_balance(user_id)

        if account_balance <= 0:
            return {
                "position_size": Decimal("0"),
                "risk_amount": Decimal("0"),
                "adjusted_stop_loss": stop_loss,
                "warning": "Account balance is zero or negative"
            }

        # Determine risk percentage
        if risk_percent:
            risk_pct = risk_percent
        elif profile.risk_per_trade_custom:
            risk_pct = profile.risk_per_trade_custom
        else:
            risk_pct = profile.risk_per_trade_percent

        risk_amount = account_balance * (risk_pct / Decimal("100"))

        # Calculate position size based on stop loss distance
        if stop_loss and price > 0:
            if direction == "buy":
                sl_distance = (price - stop_loss) / price
            else:
                sl_distance = (stop_loss - price) / price

            if sl_distance > 0:
                position_size = risk_amount / (sl_distance * price)
            else:
                position_size = risk_amount / price
        else:
            # Fixed percentage position sizing
            position_size = risk_amount / price

        # Round to reasonable precision
        position_size = position_size.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)

        # Adjust stop loss if not provided
        adjusted_sl = stop_loss
        if not stop_loss and profile.mandatory_stop_loss:
            atr_multiplier = Decimal("1.5")
            sl_distance = price * (risk_pct / Decimal("100")) * atr_multiplier
            if direction == "buy":
                adjusted_sl = price - sl_distance
            else:
                adjusted_sl = price + sl_distance

        return {
            "position_size": position_size,
            "risk_amount": risk_amount,
            "adjusted_stop_loss": adjusted_sl,
            "warning": None
        }

    async def _get_account_balance(self, user_id: int) -> Decimal:
        """Get account balance from latest trade or default."""
        # Try to get from cache first
        cache_key = f"balance:{user_id}"
        cached = await redis_client.get(cache_key)
        if cached:
            return Decimal(cached)

        # Default paper balance
        return Decimal("100000.00")

    async def _log_risk_event(
        self,
        user_id: int,
        event_type: RiskEventType,
        message: str,
        symbol: Optional[str] = None
    ):
        """Log risk event to database."""
        event = RiskEvent(
            user_id=user_id,
            event_type=event_type,
            severity="critical" if event_type in [
                RiskEventType.MAX_DRAWDOWN,
                RiskEventType.DAILY_LOSS_LIMIT,
                RiskEventType.WEEKLY_LOSS_LIMIT,
                RiskEventType.MONTHLY_LOSS_LIMIT
            ] else "warning",
            message=message,
            symbol=symbol
        )
        self.db.add(event)
        await self.db.commit()

        logger.warning(f"RISK EVENT: {event_type.value} - {message} (User: {user_id})")

    async def update_trade_result(self, user_id: int, pnl: Decimal):
        """Update risk metrics after trade close."""
        profile = await self._get_risk_profile(user_id)
        if not profile:
            return

        if pnl < 0:
            profile.consecutive_losses += 1
            profile.current_daily_loss = Decimal(str(profile.current_daily_loss)) + abs(pnl)
            profile.current_weekly_loss = Decimal(str(profile.current_weekly_loss)) + abs(pnl)
            profile.current_monthly_loss = Decimal(str(profile.current_monthly_loss)) + abs(pnl)
        else:
            profile.consecutive_losses = 0

        # Recalculate drawdown
        # (Simplified - in production would track peak equity)
        balance = await self._get_account_balance(user_id)
        if balance > 0:
            total_loss = float(profile.current_daily_loss) + float(profile.current_weekly_loss)
            profile.current_drawdown = Decimal(str(min(total_loss / float(balance) * 100, 99.99)))

        await self.db.commit()

    async def reset_daily_limits(self):
        """Reset daily loss counters (run at midnight)."""
        await self.db.execute(
            select(RiskProfile)
        )
        # This would be implemented with a scheduled job
        pass

    async def pause_trading(self, user_id: int, reason: str) -> bool:
        """Manually pause trading for user."""
        profile = await self._get_risk_profile(user_id)
        if profile:
            profile.trading_paused = True
            profile.pause_reason = reason
            profile.paused_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._log_risk_event(user_id, RiskEventType.MANUAL_PAUSE, reason)
            return True
        return False

    async def resume_trading(self, user_id: int) -> bool:
        """Resume trading for user."""
        profile = await self._get_risk_profile(user_id)
        if profile:
            profile.trading_paused = False
            profile.pause_reason = None
            profile.paused_at = None
            await self.db.commit()

            logger.info(f"Trading resumed for user {user_id}")
            return True
        return False

    async def check_spread_protection(self, symbol: str, spread: Decimal, price: Decimal, profile: RiskProfile) -> bool:
        """Check spread protection."""
        if not profile.spread_protection_enabled:
            return True

        spread_pct = (spread / price) * 100
        max_spread = Decimal(str(profile.max_spread_pips)) / 100  # Convert pips to percentage

        if spread_pct > max_spread:
            await self._log_risk_event(
                profile.user_id,
                RiskEventType.SPREAD_PROTECTION,
                f"Spread {spread_pct:.4f}% exceeds max {max_spread:.4f}% for {symbol}"
            )
            return False

        return True

    async def check_volatility_protection(self, volatility: Decimal, price: Decimal, profile: RiskProfile) -> bool:
        """Check volatility protection."""
        if not profile.volatility_protection_enabled:
            return True

        vol_pct = (volatility / price) * 100
        max_vol = Decimal(str(profile.max_volatility_percent))

        if vol_pct > max_vol:
            await self._log_risk_event(
                profile.user_id,
                RiskEventType.VOLATILITY_PROTECTION,
                f"Volatility {vol_pct:.2f}% exceeds max {max_vol:.2f}%"
            )
            return False

        return True
