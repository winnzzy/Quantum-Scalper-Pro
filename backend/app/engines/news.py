"""Economic calendar risk filter for high-impact market events."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import logger
from app.core.redis import redis_client


class NewsFilter:
    """Block new entries around relevant high-impact economic releases."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.events: List[Dict[str, Any]] = []
        self.is_active = settings.NEWS_FILTER_ENABLED
        self.high_impact_keywords = [value.lower() for value in settings.HIGH_IMPACT_EVENTS]
        self.buffer_minutes = settings.NEWS_BUFFER_MINUTES
        self.last_successful_update: Optional[datetime] = None

    async def start(self):
        if not self.is_active:
            return
        await self._fetch_economic_calendar()
        self.scheduler.add_job(
            self._fetch_economic_calendar,
            "interval",
            minutes=30,
            id="news_update",
            replace_existing=True,
            max_instances=1,
        )
        if not self.scheduler.running:
            self.scheduler.start()
        logger.info("News filter started")

    async def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        logger.info("News filter stopped")

    async def _fetch_economic_calendar(self):
        """Fetch and normalize the configured economic calendar."""
        if not settings.NEWS_API_KEY:
            logger.error("NEWS_API_KEY is missing; economic calendar is unavailable")
            return

        now = datetime.now(timezone.utc)
        params = {
            "from": now.date().isoformat(),
            "to": (now + timedelta(days=7)).date().isoformat(),
            "token": settings.NEWS_API_KEY,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(settings.NEWS_API_URL, params=params)
                response.raise_for_status()
                payload = response.json()

            raw_events = payload.get("economicCalendar", payload if isinstance(payload, list) else [])
            normalized = [
                event
                for item in raw_events
                if (event := self._normalize_event(item)) is not None
            ]
            normalized.sort(key=lambda event: event["time"])

            self.events = normalized
            self.last_successful_update = now
            await redis_client.set_json("economic_calendar", self.events, expire=3600)
            logger.info(f"Updated economic calendar: {len(self.events)} relevant events")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.error(f"Failed to fetch economic calendar: {exc}")

    def _normalize_event(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = str(item.get("event") or item.get("title") or "").strip()
        impact = str(item.get("impact") or "").strip().lower()
        if impact and impact not in {"high", "3"}:
            return None
        if not impact and not any(keyword in title.lower() for keyword in self.high_impact_keywords):
            return None

        raw_time = item.get("time") or item.get("datetime") or item.get("date")
        event_time = self._parse_time(raw_time)
        if event_time is None:
            return None

        return {
            "id": str(item.get("id") or f"{title}:{event_time.isoformat()}"),
            "title": title or "Economic event",
            "time": event_time.isoformat(),
            "impact": "high",
            "currency": str(item.get("currency") or item.get("country") or "").upper(),
            "forecast": item.get("estimate") or item.get("forecast"),
            "previous": item.get("prev") or item.get("previous"),
            "actual": item.get("actual"),
        }

    @staticmethod
    def _parse_time(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value, tz=timezone.utc)
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError, OSError):
            return None

    def _data_is_stale(self) -> bool:
        if self.last_successful_update is None:
            return True
        age = datetime.now(timezone.utc) - self.last_successful_update
        return age > timedelta(minutes=settings.NEWS_MAX_STALENESS_MINUTES)

    @staticmethod
    def _symbol_currencies(symbol: str) -> set[str]:
        clean = symbol.upper().replace("/", "").replace("-", "").replace("_", "")
        known = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
        return {currency for currency in known if currency in clean}

    def is_news_lock_active(self, symbol: str = "") -> Dict[str, Any]:
        if not self.is_active:
            return {"active": False, "reason": "News filter disabled"}

        if self._data_is_stale():
            active = settings.NEWS_FAIL_CLOSED
            return {
                "active": active,
                "reason": "Economic calendar data unavailable or stale",
                "data_available": False,
            }

        now = datetime.now(timezone.utc)
        currencies = self._symbol_currencies(symbol)
        for event in self.events:
            event_currency = event.get("currency", "")
            if currencies and event_currency and event_currency not in currencies:
                continue

            event_time = datetime.fromisoformat(event["time"])
            minutes = (event_time - now).total_seconds() / 60
            if abs(minutes) <= self.buffer_minutes:
                return {
                    "active": True,
                    "reason": f"High impact event: {event['title']} at {event_time:%H:%M UTC}",
                    "next_event": event,
                    "time_until_release": int(minutes),
                    "data_available": True,
                }

        return {"active": False, "reason": "No active news lock", "data_available": True}

    def should_trade(self, symbol: str = "") -> bool:
        return not self.is_news_lock_active(symbol)["active"]

    def get_upcoming_events(self, hours: int = 24) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)
        return [
            event
            for event in self.events
            if now <= datetime.fromisoformat(event["time"]) <= cutoff
        ]

    async def add_custom_event(self, title: str, event_time: datetime, impact: str = "high"):
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        event = {
            "id": f"custom_{int(event_time.timestamp())}",
            "title": title,
            "time": event_time.astimezone(timezone.utc).isoformat(),
            "impact": impact,
            "currency": "",
            "forecast": None,
            "previous": None,
            "actual": None,
        }
        self.events.append(event)
        self.events.sort(key=lambda item: item["time"])
        await redis_client.set_json("economic_calendar", self.events, expire=3600)


news_filter = NewsFilter()
