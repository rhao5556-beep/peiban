import uuid

import pytest
from fastapi import HTTPException

from app.api.endpoints.profile import update_user_settings, UserSettingsUpdateRequest
from app.core.config import settings


class DummyResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class DummyDB:
    def __init__(self, user):
        self._user = user
        self.committed = 0

    async def execute(self, *args, **kwargs):
        return DummyResult(self._user)

    async def commit(self):
        self.committed += 1

    async def refresh(self, *args, **kwargs):
        return None


class DummyUser:
    def __init__(self, user_id):
        self.id = user_id
        self.settings = {}


@pytest.mark.asyncio
async def test_update_user_settings_rejects_too_large(monkeypatch):
    monkeypatch.setattr(settings, "JSON_FIELD_MAX_BYTES", 50)
    user_id = str(uuid.uuid4())
    user = DummyUser(uuid.UUID(user_id))
    db = DummyDB(user)

    big_value = "x" * 1000
    req = UserSettingsUpdateRequest(ui={"blob": big_value})

    with pytest.raises(HTTPException) as excinfo:
        await update_user_settings(
            user_id=user_id,
            request=req,
            current_user={"user_id": user_id},
            db=db,
        )
    assert excinfo.value.status_code == 413

