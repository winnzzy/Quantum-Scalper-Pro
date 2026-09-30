"""Cross-process operational safety state."""
from app.core.config import settings
from app.core.redis import redis_client

EMERGENCY_STOP_KEY = "qsp:operational:emergency_stop"


async def emergency_stop_active() -> bool:
    if settings.EMERGENCY_STOP:
        return True
    if not redis_client.is_healthy:
        return False
    return await redis_client.get(EMERGENCY_STOP_KEY) == "active"


async def activate_emergency_stop() -> None:
    settings.EMERGENCY_STOP = True
    await redis_client.set(EMERGENCY_STOP_KEY, "active", expire=None)


async def clear_emergency_stop() -> None:
    settings.EMERGENCY_STOP = False
    await redis_client.delete(EMERGENCY_STOP_KEY)
