import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import create_refresh_token, verify_refresh_token, revoke_token_jti, is_token_revoked


class DummyRedis:
    def __init__(self):
        self._store = {}

    async def set(self, key, value, ex=None):
        self._store[key] = value
        return True

    async def get(self, key):
        return self._store.get(key)


@pytest.mark.asyncio
async def test_refresh_token_can_be_revoked(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "x" * 64)
    monkeypatch.setattr(settings, "JWT_REFRESH_EXPIRE_DAYS", 14)

    dummy_redis = DummyRedis()
    import app.core.database as database

    monkeypatch.setattr(database, "get_redis_client", lambda: dummy_redis)

    user_id = "test-user-id"
    token = create_refresh_token(user_id=user_id)
    payload = await verify_refresh_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"

    await revoke_token_jti(payload.get("jti"), payload.get("exp"))
    assert await is_token_revoked(payload.get("jti")) is True

    with pytest.raises(HTTPException) as excinfo:
        await verify_refresh_token(token)
    assert excinfo.value.status_code == 401

