import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.middleware.rate_limit import RateLimitMiddleware


class FakeRedis:
    def __init__(self):
        self._data = {}

    async def incr(self, key: str) -> int:
        self._data[key] = int(self._data.get(key, 0)) + 1
        return int(self._data[key])

    async def expire(self, key: str, ttl: int) -> bool:
        return True


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_limit():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_minute=2, redis_client=FakeRedis())

    @app.get("/x")
    async def x():
        return {"ok": True}

    async with AsyncClient(app=app, base_url="http://test") as client:
        r1 = await client.get("/x")
        r2 = await client.get("/x")
        r3 = await client.get("/x")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429

