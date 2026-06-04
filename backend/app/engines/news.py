"""News Filter - Avoid trading during high impact events."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import logger
from app.core.redis import redis_client


class NewsFilter:
    """
    News Filter - Economic calendar integration.

    Avoids trading during:
    - NFP (Non-Farm Payrolls)
    - CPI (Consumer Price Index)
    - Interest Rate Decisions
    - High Impact News
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.events: List[Dict[str, Any]] = []
        self.is_active = settings.NEWS_FILTER_ENABLED
        self.high_impact_keywords = settings.HIGH_IMPACT_EVENTS
        self.buffer_minutes = settings.NEWS_BUFFER_MINUTES

    async def start(self):
        """Start news filter scheduler."""
        if not self.is_active:
            return

        # Fetch initial data
        await self._fetch_economic_calendar()

        # Schedule updates every hour
        self.scheduler.add_job(
            self._fetch_economic_calendar,
            "interval",
            minutes=60,
            id="news_update",
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("News filter started")

    async def stop(self):
        """Stop news filter."""
        self.scheduler.shutdown()
        logger.info("News filter stopped")

    async def _fetch_economic_calendar(self):
        """Fetch economic calendar data."""
        try:
            # Using ForexFactory calendar API (or similar)
            # In production, use a proper economic calendar API

            # For demo, we'll create mock events based on known schedules
            self.events = self._generate_mock_events()

            # Cache in Redis
            await redis_client.set_json(
                "economic_calendar",
                self.events,
                expire=3600
            )

            logger.info(f"Updated economic calendar: {len(self.events)} events")

        except Exception as e:
            logger.error(f"Failed to fetch economic calendar: {e}")

    def _generate_mock_events(self) -> List[Dict[str, Any]]:
        """Generate mock economic events for demonstration."""
        now = datetime.now(timezone.utc)
        events = []

        # NFP - First Friday of month at 13:30 UTC
        # CPI - Monthly around mid-month
        # FOMC - 8 times per year

        # For demo, add some events around current time
        for i in range(5):
            event_time = now + timedelta(hours=i*6)
            events.append({
                "id": f"event_{i}",
                "title": random.choice(["NFP", "CPI", "FOMC", "GDP", "Interest Rate"]),
                "time": event_time.isoformat(),
                "impact": "high",
                "currency": "USD",
                "forecast": "",
                "previous": ""
            })

        return events

    def is_news_lock_active(self, symbol: str = "") -> Dict[str, Any]:
        """
        Check if news lock is active.

        Returns:
            {
                "active": bool,
                "reason": str,
                "next_event": Optional[dict],
                "time_until_release": Optional[int]  # minutes
            }
        """
        if not self.is_active:
            return {"active": False, "reason": "News filter disabled"}

        now = datetime.now(timezone.utc)

        for event in self.events:
            event_time = datetime.fromisoformat(event["time"])
            time_diff = (event_time - now).total_seconds() / 60  # minutes

            # Check if within buffer period
            if abs(time_diff) <= self.buffer_minutes:
                return {
                    "active": True,
                    "reason": f"High impact event: {event['title']} at {event_time.strftime('%H:%M UTC')}",
                    "next_event": event,
                    "time_until_release": int(time_diff)
                }

        return {"active": False, "reason": "No active news lock"}

    def should_trade(self, symbol: str = "") -> bool:
        """Quick check if trading should be allowed."""
        result = self.is_news_lock_active(symbol)
        return not result["active"]

    def get_upcoming_events(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get upcoming high impact events."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)

        upcoming = []
        for event in self.events:
            event_time = datetime.fromisoformat(event["time"])
            if now <= event_time <= cutoff:
                upcoming.append(event)

        return upcoming

    async def add_custom_event(self, title: str, event_time: datetime, impact: str = "high"):
        """Add custom news event."""
        event = {
            "id": f"custom_{int(event_time.timestamp())}",
            "title": title,
            "time": event_time.isoformat(),
            "impact": impact,
            "currency": "",
            "forecast": "",
            "previous": ""
        }
        self.events.append(event)

        await redis_client.set_json("economic_calendar", self.events, expire=3600)
        logger.info(f"Custom event added: {title} at {event_time}")


import random

# Global instance
news_filter = NewsFilter()
