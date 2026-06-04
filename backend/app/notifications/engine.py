"""Notification Engine - Telegram and Email notifications."""
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from telegram import Bot
from telegram.constants import ParseMode
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings
from app.core.logging import logger
from app.core.redis import redis_client
from app.models.system import Notification


class NotificationEngine:
    """
    Notification Engine.

    Channels:
    - Telegram
    - Email
    - Web (in-app)

    Events:
    - Trade Open
    - Trade Close
    - Stop Loss Hit
    - Take Profit Hit
    - Daily Summary
    - Weekly Summary
    - Critical Errors
    """

    def __init__(self):
        self.telegram_bot: Optional[Bot] = None
        self.telegram_chat_id: Optional[str] = None
        self._init_telegram()

    def _init_telegram(self):
        """Initialize Telegram bot."""
        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
            self.telegram_bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            self.telegram_chat_id = settings.TELEGRAM_CHAT_ID
            logger.info("Telegram notifications initialized")

    async def send_trade_notification(
        self,
        user_id: int,
        event_type: str,
        trade: Any,
        channels: Optional[List[str]] = None
    ):
        """Send trade-related notification."""
        if not channels:
            channels = ["web"]
            if self.telegram_bot:
                channels.append("telegram")
            if settings.SMTP_HOST:
                channels.append("email")

        # Build message
        message = self._build_trade_message(event_type, trade)

        # Send to all channels
        for channel in channels:
            try:
                if channel == "telegram" and self.telegram_bot:
                    await self._send_telegram(message["telegram"])
                elif channel == "email" and settings.SMTP_HOST:
                    await self._send_email(
                        to_email=trade.user.email if hasattr(trade, 'user') else "",
                        subject=message["subject"],
                        body=message["email"]
                    )
                elif channel == "web":
                    await self._send_web_notification(user_id, event_type, message["web"])
            except Exception as e:
                logger.error(f"Failed to send {channel} notification: {e}")

    async def send_summary(self, user_id: int, period: str = "daily"):
        """Send daily/weekly summary."""
        # This would query trade statistics and send summary
        pass

    async def send_alert(self, user_id: int, title: str, message: str, priority: str = "normal"):
        """Send general alert."""
        notification = {
            "title": title,
            "message": message,
            "priority": priority,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self._send_web_notification(user_id, "alert", notification)

        if priority == "critical" and self.telegram_bot:
            await self._send_telegram(f"🚨 *CRITICAL ALERT*

*{title}*
{message}")

    def _build_trade_message(self, event_type: str, trade: Any) -> Dict[str, str]:
        """Build formatted messages for different channels."""
        symbol = trade.symbol if hasattr(trade, 'symbol') else "Unknown"
        direction = trade.direction.value if hasattr(trade, 'direction') else ""
        price = trade.entry_price if hasattr(trade, 'entry_price') else 0
        pnl = trade.net_pnl if hasattr(trade, 'net_pnl') else 0

        emoji = "🟢" if event_type == "trade_open" else "🔴" if event_type == "trade_close" else "⚠️"

        telegram_msg = f"""{emoji} *Trade {event_type.replace('_', ' ').title()}*

Symbol: `{symbol}`
Direction: {direction.upper()}
Price: {price}
P&L: {pnl}
"""

        if event_type == "stop_loss_hit":
            telegram_msg = f"🛑 *Stop Loss Hit*

Symbol: `{symbol}`
P&L: {pnl}"
        elif event_type == "take_profit_hit":
            telegram_msg = f"🎯 *Take Profit Hit*

Symbol: `{symbol}`
P&L: {pnl}"

        web_msg = {
            "title": f"Trade {event_type.replace('_', ' ').title()}",
            "body": f"{symbol} {direction} @ {price}",
            "pnl": str(pnl),
            "trade_id": trade.id if hasattr(trade, 'id') else None
        }

        return {
            "telegram": telegram_msg,
            "email": telegram_msg.replace("*", "").replace("`", ""),
            "subject": f"Quantum Scalper Pro - {event_type.replace('_', ' ').title()}",
            "web": web_msg
        }

    async def _send_telegram(self, message: str):
        """Send Telegram message."""
        if not self.telegram_bot or not self.telegram_chat_id:
            return

        try:
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def _send_email(self, to_email: str, subject: str, body: str):
        """Send email notification."""
        if not settings.SMTP_HOST or not settings.SMTP_USER:
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = settings.SMTP_USER
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                start_tls=settings.SMTP_TLS
            )
        except Exception as e:
            logger.error(f"Email send failed: {e}")

    async def _send_web_notification(self, user_id: int, type: str, data: Dict[str, Any]):
        """Send web notification via Redis pub/sub."""
        notification = {
            "user_id": user_id,
            "type": type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await redis_client.publish(f"notifications:{user_id}", str(notification))

        # Also store in Redis list for retrieval
        await redis_client.lpush(
            f"notifications_list:{user_id}",
            str(notification)
        )


# Global instance
notification_engine = NotificationEngine()
