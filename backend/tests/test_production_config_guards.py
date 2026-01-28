import pytest

from app.core.config import settings
from app.core.startup_checks import validate_production_settings


@pytest.mark.asyncio
async def test_production_requires_token_issue_secret(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "JWT_SECRET", "x" * 64)
    monkeypatch.setattr(settings, "TOKEN_ISSUE_SECRET", "")
    monkeypatch.setattr(settings, "AUTH_SESSION_SECRET", "y" * 64)
    monkeypatch.setattr(settings, "AUTH_ALLOW_CLIENT_USER_ID", False)

    with pytest.raises(RuntimeError):
        validate_production_settings(settings)


@pytest.mark.asyncio
async def test_production_requires_auth_session_secret(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "JWT_SECRET", "x" * 64)
    monkeypatch.setattr(settings, "TOKEN_ISSUE_SECRET", "t" * 32)
    monkeypatch.setattr(settings, "AUTH_SESSION_SECRET", "")
    monkeypatch.setattr(settings, "AUTH_ALLOW_CLIENT_USER_ID", False)

    with pytest.raises(RuntimeError):
        validate_production_settings(settings)
