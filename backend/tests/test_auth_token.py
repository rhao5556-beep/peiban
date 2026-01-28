import pytest
import uuid

from fastapi import HTTPException
from starlette.responses import Response

from app.api.endpoints.auth import get_token, TokenRequest
from app.core.ids import normalize_uuid
from app.core.security import verify_token
from app.core.config import settings


class DummySession:
    async def execute(self, *args, **kwargs):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


class DummyRequest:
    def __init__(self, host: str = "127.0.0.1", headers: dict | None = None, cookies: dict | None = None):
        self.client = type("Client", (), {"host": host})()
        self.headers = headers or {}
        self.cookies = cookies or {}


@pytest.mark.asyncio
async def test_token_requires_issue_secret_in_production(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "TOKEN_ISSUE_SECRET", "secret")
    monkeypatch.setattr(settings, "JWT_SECRET", "x" * 64)

    with pytest.raises(HTTPException) as excinfo:
        await get_token(
            http_request=DummyRequest(host="1.2.3.4"),
            http_response=Response(),
            request=TokenRequest(),
            db=DummySession(),
            token_issue_secret=None
        )
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_token_sub_matches_client_user_id_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "AUTH_ALLOW_CLIENT_USER_ID", True)
    monkeypatch.setattr(settings, "JWT_SECRET", "x" * 64)

    requested = "user-123"
    token = await get_token(
        http_request=DummyRequest(host="1.2.3.4"),
        http_response=Response(),
        request=TokenRequest(user_id=requested),
        db=DummySession(),
        token_issue_secret=None
    )
    payload = verify_token(token.access_token)
    assert payload["sub"] == normalize_uuid(requested)


@pytest.mark.asyncio
async def test_token_uses_session_cookie_without_issue_secret(monkeypatch):
    from app.api.endpoints import auth as auth_endpoint

    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "TOKEN_ISSUE_SECRET", "secret")
    monkeypatch.setattr(settings, "AUTH_SESSION_SECRET", "cookie-secret")
    monkeypatch.setattr(settings, "JWT_SECRET", "x" * 64)

    user_id = str(uuid.uuid4())
    cookie_name = settings.AUTH_SESSION_COOKIE_NAME
    cookie_value = auth_endpoint._make_session_cookie(user_id, settings.AUTH_SESSION_SECRET)

    token = await get_token(
        http_request=DummyRequest(host="1.2.3.4", cookies={cookie_name: cookie_value}),
        http_response=Response(),
        request=TokenRequest(),
        db=DummySession(),
        token_issue_secret=None,
    )
    payload = verify_token(token.access_token)
    assert payload["sub"] == user_id
