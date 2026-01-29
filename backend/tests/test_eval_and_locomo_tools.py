import json
import uuid
import sys
from pathlib import Path
import importlib.util

import pytest
from fastapi.responses import JSONResponse

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

def _load_module_from_path(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeScalarResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeAsyncSession:
    async def execute(self, stmt):
        return _FakeScalarResult(None)

    def add(self, obj):
        return None

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_send_message_eval_mode_returns_structured_500(monkeypatch):
    from app.api.endpoints import conversation as conv

    class _FakeGraphService:
        def __init__(self, neo4j_driver=None):
            self.driver = None

    class _FakeRetrievalService:
        def __init__(self, milvus_client=None, graph_service=None, db_session=None):
            self.milvus = None
            self.graph = None
            self.db = db_session

    class _FakeAffinityService:
        pass

    class _FakeConversationService:
        def __init__(self, affinity_service=None, retrieval_service=None, graph_service=None):
            pass

        async def process_message(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(conv, "get_neo4j_driver", lambda: None)
    monkeypatch.setattr(conv, "get_milvus_collection", lambda: None)
    monkeypatch.setattr(conv, "GraphService", _FakeGraphService)
    monkeypatch.setattr(conv, "RetrievalService", _FakeRetrievalService)
    monkeypatch.setattr(conv, "AffinityService", _FakeAffinityService)
    monkeypatch.setattr(conv, "ConversationService", _FakeConversationService)

    req = conv.MessageRequest(message="hi", mode="graph_only", eval_mode=True)
    resp = await conv.send_message(
        request=req,
        current_user={"user_id": str(uuid.uuid4())},
        db=_FakeAsyncSession(),
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 500
    body = json.loads(resp.body.decode("utf-8"))
    assert body["error_code"] == "CONVERSATION_FAILED"
    assert body["message"] == "conversation_failed"
    assert "trace_id" in body and body["trace_id"]
    assert resp.headers.get("x-trace-id") == body["trace_id"]


@pytest.mark.asyncio
async def test_send_message_non_eval_returns_fallback_message_response(monkeypatch):
    from app.api.endpoints import conversation as conv

    class _FakeGraphService:
        def __init__(self, neo4j_driver=None):
            self.driver = None

    class _FakeRetrievalService:
        def __init__(self, milvus_client=None, graph_service=None, db_session=None):
            self.milvus = None
            self.graph = None
            self.db = db_session

    class _FakeAffinityService:
        pass

    class _FakeConversationService:
        def __init__(self, affinity_service=None, retrieval_service=None, graph_service=None):
            pass

        async def process_message(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(conv, "get_neo4j_driver", lambda: None)
    monkeypatch.setattr(conv, "get_milvus_collection", lambda: None)
    monkeypatch.setattr(conv, "GraphService", _FakeGraphService)
    monkeypatch.setattr(conv, "RetrievalService", _FakeRetrievalService)
    monkeypatch.setattr(conv, "AffinityService", _FakeAffinityService)
    monkeypatch.setattr(conv, "ConversationService", _FakeConversationService)

    req = conv.MessageRequest(message="hi", mode="graph_only", eval_mode=False)
    resp = await conv.send_message(
        request=req,
        current_user={"user_id": str(uuid.uuid4())},
        db=_FakeAsyncSession(),
    )

    assert isinstance(resp, conv.MessageResponse)
    assert resp.error_code == "CONVERSATION_FAILED"
    assert resp.trace_id
    assert "抱歉" in resp.reply


def test_locomo_scorer_reads_top_level_fields():
    mod = _load_module_from_path(
        "local_score_locomo_with_llm",
        _ROOT / "evals" / "score_locomo_with_llm.py",
    )
    score_outputs_with_llm = mod.score_outputs_with_llm

    items = [
        {
            "id": 1,
            "task_type": "demo_task",
            "category": 2,
            "question": "When did Caroline go to the LGBTQ support group?",
            "reference_answer": "7 May 2023",
            "model_answer": "2023-05-07",
            "meta": {},
        },
        {
            "id": 2,
            "task_type": "",
            "category": 1,
            "question": "What is Caroline's relationship status?",
            "reference_answer": "Single",
            "model_answer": "I don't know.",
            "meta": {},
        },
    ]

    summary, scored = score_outputs_with_llm(items, use_llm=False)
    assert summary["total"] == 2
    assert summary["correct"] == 1
    assert "2" in summary["by_category"]
    assert summary["by_category"]["2"]["correct"] == 1
    assert "demo_task" in summary["by_task_type"]
    assert "unknown" in summary["by_task_type"]
    assert len(scored) == 2


def test_locomo_report_supports_zh():
    mod = _load_module_from_path(
        "local_generate_locomo_report",
        _ROOT / "evals" / "generate_locomo_report.py",
    )
    generate_report = mod.generate_report

    report = generate_report(
        summary={
            "total": 2,
            "correct": 1,
            "accuracy": 0.5,
            "exact_match_accuracy": 0.5,
            "avg_confidence": 1.0,
            "scoring_method": "exact_match",
            "by_category": {"2": {"category_name": "Temporal Understanding", "total": 2, "correct": 1, "accuracy": 0.5, "exact_match_accuracy": 0.5, "avg_confidence": 1.0}},
            "by_task_type": {"demo": {"total": 2, "correct": 1, "accuracy": 0.5, "exact_match_accuracy": 0.5, "avg_confidence": 1.0}},
        },
        failures=[],
        lang="zh",
    )
    assert "LoCoMo 评测报告" in report
    assert "总体表现" in report
    assert "评分方式" in report
