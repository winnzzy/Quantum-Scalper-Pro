"""Redis client configuration."""
import json
from typing import Any, Optional

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import logger


class RedisClient:
    """Async Redis client wrapper."""

    def __init__(self):
        self._client: Optional[redis.Redis] = None

    async def connect(self):
        """Initialize Redis connection."""
        if self._client is None:
            self._client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                password=settings.REDIS_PASSWORD
            )
            logger.info("Redis connection established")

    async def disconnect(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        await self.connect()
        return await self._client.get(key)

    async def set(self, key: str, value: str, expire: int = 3600) -> bool:
        """Set value with optional expiration."""
        await self.connect()
        return await self._client.set(key, value, ex=expire)

    async def delete(self, key: str) -> int:
        """Delete key."""
        await self.connect()
        return await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        await self.connect()
        return await self._client.exists(key) > 0

    async def hset(self, name: str, key: str, value: str) -> int:
        """Set hash field."""
        await self.connect()
        return await self._client.hset(name, key, value)

    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field."""
        await self.connect()
        return await self._client.hget(name, key)

    async def hgetall(self, name: str) -> dict:
        """Get all hash fields."""
        await self.connect()
        return await self._client.hgetall(name)

    async def publish(self, channel: str, message: str) -> int:
        """Publish message to channel."""
        await self.connect()
        return await self._client.publish(channel, message)

    async def lpush(self, key: str, value: str) -> int:
        """Push to list."""
        await self.connect()
        return await self._client.lpush(key, value)

    async def lrange(self, key: str, start: int, end: int) -> list:
        """Get list range."""
        await self.connect()
        return await self._client.lrange(key, start, end)

    async def set_json(self, key: str, value: Any, expire: int = 3600) -> bool:
        """Store JSON serializable object."""
        await self.connect()
        return await self._client.set(key, json.dumps(value), ex=expire)

    async def get_json(self, key: str) -> Optional[Any]:
        """Retrieve JSON object."""
        await self.connect()
        data = await self._client.get(key)
        return json.loads(data) if data else None


# Global instance
redis_client = RedisClient()
