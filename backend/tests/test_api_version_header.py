import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.middleware.api_version import ApiVersionMiddleware


@pytest.mark.asyncio
async def test_api_version_header_is_set():
    app = FastAPI()
    app.add_middleware(ApiVersionMiddleware, default_version="v1")

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/api/v1/ping")
    assert r.headers.get("X-API-Version") == "v1"

