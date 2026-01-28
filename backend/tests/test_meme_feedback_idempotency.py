import uuid

import pytest

from app.models.meme_usage_history import MemeUsageHistory
from app.services.meme_usage_history_service import MemeUsageHistoryService


class DummyResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class DummyDB:
    def __init__(self, obj):
        self._obj = obj
        self.committed = 0
        self.rolled_back = 0

    async def execute(self, *args, **kwargs):
        return DummyResult(self._obj)

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


@pytest.mark.asyncio
async def test_record_feedback_sets_reaction_once():
    user_id = uuid.uuid4()
    usage = MemeUsageHistory(id=uuid.uuid4(), user_id=user_id, meme_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    usage.user_reaction = None
    service = MemeUsageHistoryService(DummyDB(usage))

    ok = await service.record_feedback(usage_id=usage.id, user_id=user_id, reaction="liked")
    assert ok is True
    assert usage.user_reaction == "liked"
    assert service.db.committed == 1


@pytest.mark.asyncio
async def test_record_feedback_is_idempotent_when_same_reaction():
    user_id = uuid.uuid4()
    usage = MemeUsageHistory(id=uuid.uuid4(), user_id=user_id, meme_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    usage.user_reaction = "liked"
    service = MemeUsageHistoryService(DummyDB(usage))

    ok = await service.record_feedback(usage_id=usage.id, user_id=user_id, reaction="liked")
    assert ok is True
    assert service.db.committed == 0


@pytest.mark.asyncio
async def test_record_feedback_rejects_second_change():
    user_id = uuid.uuid4()
    usage = MemeUsageHistory(id=uuid.uuid4(), user_id=user_id, meme_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    usage.user_reaction = "liked"
    service = MemeUsageHistoryService(DummyDB(usage))

    ok = await service.record_feedback(usage_id=usage.id, user_id=user_id, reaction="disliked")
    assert ok is False
    assert service.db.committed == 0

