"""Redis client configuration with failure recovery."""
import json
import asyncio
from typing import Any, Optional

import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError, RedisError

from app.core.config import settings
from app.core.logging import logger


class RedisClient:
    """Async Redis client with automatic reconnection and graceful degradation."""

    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._connected: bool = False
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 10
        self._reconnect_delay: float = 1.0  # seconds
        self._circuit_open: bool = False
        self._circuit_open_until: float = 0
        self._failure_count: int = 0
        self._circuit_threshold: int = 5  # failures before opening circuit
        self._circuit_timeout: float = 30.0  # seconds to wait before retry

    async def connect(self):
        """Initialize Redis connection with retry logic."""
        if self._client is not None and self._connected:
            return

        try:
            self._client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                password=settings.REDIS_PASSWORD,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Verify connection
            await self._client.ping()
            self._connected = True
            self._reconnect_attempts = 0
            self._failure_count = 0
            self._circuit_open = False
            logger.info("Redis connection established")
        except (ConnectionError, TimeoutError, OSError) as e:
            self._connected = False
            self._failure_count += 1
            logger.error(f"Redis connection failed (attempt {self._reconnect_attempts + 1}): {e}")
            if self._failure_count >= self._circuit_threshold:
                self._circuit_open = True
                import time
                self._circuit_open_until = time.monotonic() + self._circuit_timeout
                logger.warning(f"Redis circuit breaker OPEN for {self._circuit_timeout}s")
            raise

    async def _ensure_connected(self) -> bool:
        """Ensure Redis is connected, with auto-reconnect. Returns False if unavailable."""
        import time

        # Check circuit breaker
        if self._circuit_open:
            if time.monotonic() < self._circuit_open_until:
                return False
            # Half-open: try again
            self._circuit_open = False
            logger.info("Redis circuit breaker HALF-OPEN, attempting reconnect")

        if self._client is not None and self._connected:
            try:
                await self._client.ping()
                return True
            except (ConnectionError, TimeoutError, RedisError):
                self._connected = False

        # Attempt reconnection
        for attempt in range(self._max_reconnect_attempts):
            try:
                await self.connect()
                return True
            except (ConnectionError, TimeoutError, OSError):
                delay = min(self._reconnect_delay * (2 ** attempt), 30.0)
                await asyncio.sleep(delay)
                self._reconnect_attempts += 1

        logger.error("Redis: all reconnect attempts exhausted")
        return False

    async def _execute(self, operation_name: str, func, *args, **kwargs) -> Any:
        """Execute a Redis operation with error handling and auto-reconnect."""
        try:
            if not await self._ensure_connected():
                logger.warning(f"Redis unavailable, operation '{operation_name}' skipped")
                return None
            result = await func(*args, **kwargs)
            # Reset failure count on success
            if self._failure_count > 0:
                self._failure_count = 0
            return result
        except (ConnectionError, TimeoutError, RedisError) as e:
            self._connected = False
            self._failure_count += 1
            logger.error(f"Redis operation '{operation_name}' failed: {e}")
            if self._failure_count >= self._circuit_threshold:
                import time
                self._circuit_open = True
                self._circuit_open_until = time.monotonic() + self._circuit_timeout
                logger.warning(f"Redis circuit breaker OPEN after {self._failure_count} failures")
            return None
        except Exception as e:
            logger.error(f"Redis operation '{operation_name}' unexpected error: {e}")
            return None

    async def disconnect(self):
        """Close Redis connection."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            finally:
                self._client = None
                self._connected = False
                logger.info("Redis connection closed")

    async def get(self, key: str) -> Optional[str]:
        """Get value by key. Returns None if Redis unavailable."""
        async def _op():
            return await self._client.get(key)
        return await self._execute("get", _op)

    async def set(self, key: str, value: str, expire: int = 3600) -> bool:
        """Set value with optional expiration. Returns False if Redis unavailable."""
        async def _op():
            return await self._client.set(key, value, ex=expire)
        result = await self._execute("set", _op)
        return result is not None and result

    async def delete(self, key: str) -> int:
        """Delete key. Returns 0 if Redis unavailable."""
        async def _op():
            return await self._client.delete(key)
        result = await self._execute("delete", _op)
        return result or 0

    async def exists(self, key: str) -> bool:
        """Check if key exists. Returns False if Redis unavailable."""
        async def _op():
            return await self._client.exists(key)
        result = await self._execute("exists", _op)
        return result is not None and result > 0

    async def incr(self, key: str) -> Optional[int]:
        """Increment key value. Returns None if Redis unavailable."""
        async def _op():
            return await self._client.incr(key)
        return await self._execute("incr", _op)

    async def expire_key(self, key: str, seconds: int) -> bool:
        """Set expiration on key. Returns False if Redis unavailable."""
        async def _op():
            return await self._client.expire(key, seconds)
        result = await self._execute("expire", _op)
        return result is not None and result

    async def hset(self, name: str, key: str, value: str) -> int:
        """Set hash field. Returns 0 if Redis unavailable."""
        async def _op():
            return await self._client.hset(name, key, value)
        result = await self._execute("hset", _op)
        return result or 0

    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field. Returns None if Redis unavailable."""
        async def _op():
            return await self._client.hget(name, key)
        return await self._execute("hget", _op)

    async def hgetall(self, name: str) -> dict:
        """Get all hash fields. Returns empty dict if Redis unavailable."""
        async def _op():
            return await self._client.hgetall(name)
        result = await self._execute("hgetall", _op)
        return result or {}

    async def publish(self, channel: str, message: str) -> int:
        """Publish message to channel. Returns 0 if Redis unavailable."""
        async def _op():
            return await self._client.publish(channel, message)
        result = await self._execute("publish", _op)
        return result or 0

    async def lpush(self, key: str, value: str) -> int:
        """Push to list. Returns 0 if Redis unavailable."""
        async def _op():
            return await self._client.lpush(key, value)
        result = await self._execute("lpush", _op)
        return result or 0

    async def lrange(self, key: str, start: int, end: int) -> list:
        """Get list range. Returns empty list if Redis unavailable."""
        async def _op():
            return await self._client.lrange(key, start, end)
        result = await self._execute("lrange", _op)
        return result or []

    async def set_json(self, key: str, value: Any, expire: int = 3600) -> bool:
        """Store JSON serializable object."""
        async def _op():
            return await self._client.set(key, json.dumps(value), ex=expire)
        result = await self._execute("set_json", _op)
        return result is not None and result

    async def get_json(self, key: str) -> Optional[Any]:
        """Retrieve JSON object. Returns None if Redis unavailable."""
        async def _op():
            data = await self._client.get(key)
            return json.loads(data) if data else None
        return await self._execute("get_json", _op)

    async def set_nx(self, key: str, value: str, expire: int = 60) -> bool:
        """Set if not exists (for distributed locks). Returns False if Redis unavailable."""
        async def _op():
            result = await self._client.set(key, value, ex=expire, nx=True)
            return result is not None and result
        result = await self._execute("set_nx", _op)
        return result is not None and result

    async def pipeline_execute(self, operations: list) -> list:
        """Execute multiple operations in a pipeline. Returns empty list if Redis unavailable.
        
        Each operation is a tuple: (method_name, args_dict)
        Example: [("incr", {"name": "key"}), ("expire", {"name": "key", "time": 60})]
        """
        async def _op():
            pipe = self._client.pipeline()
            for method_name, kwargs in operations:
                getattr(pipe, method_name)(**kwargs)
            return await pipe.execute()
        result = await self._execute("pipeline", _op)
        return result or []

    @property
    def is_connected(self) -> bool:
        """Check if Redis is currently connected."""
        return self._connected

    @property
    def is_healthy(self) -> bool:
        """Check if Redis is healthy (connected and circuit closed)."""
        return self._connected and not self._circuit_open


# Global instance
redis_client = RedisClient()