import pytest

from app.auth.totp import generate_code, verify_code
from app.core import operational_state
from app.core.config import settings


def test_totp_known_time_and_adjacent_window():
    secret = "JBSWY3DPEHPK3PXP"
    code = generate_code(secret, at_time=1_700_000_000)
    assert verify_code(secret, code, at_time=1_700_000_000)
    assert verify_code(secret, code, at_time=1_700_000_030)
    assert not verify_code(secret, "000000", at_time=1_700_000_000)


@pytest.mark.asyncio
async def test_emergency_stop_is_written_without_expiry(monkeypatch):
    calls = []

    async def fake_set(key, value, expire=3600):
        calls.append((key, value, expire))
        return True

    previous = settings.EMERGENCY_STOP
    monkeypatch.setattr(operational_state.redis_client, "set", fake_set)
    try:
        settings.EMERGENCY_STOP = False
        await operational_state.activate_emergency_stop()
        assert settings.EMERGENCY_STOP is True
        assert calls == [(operational_state.EMERGENCY_STOP_KEY, "active", None)]
    finally:
        settings.EMERGENCY_STOP = previous
