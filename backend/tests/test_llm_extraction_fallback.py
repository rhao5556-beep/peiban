import pytest

from app.services import llm_extraction_service


def test_regex_fallback_extracts_dislike_relation(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(llm_extraction_service.client.chat.completions, "create", _boom)

    res = llm_extraction_service.extract_ir(
        text="我讨厌吃蛋糕。",
        user_id="test-user-id",
        context_entities=[],
        max_retries=0,
        timeout=0,
    )
    assert res.success is True
    assert res.metadata["source"] == "regex_fallback"
    assert any(r.get("type") == "DISLIKES" for r in res.relations)


def test_regex_fallback_skips_question_clause(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(llm_extraction_service.client.chat.completions, "create", _boom)

    res = llm_extraction_service.extract_ir(
        text="我喜欢足球。你喜欢什么？",
        user_id="test-user-id",
        context_entities=[],
        max_retries=0,
        timeout=0,
    )
    assert res.success is True
    assert any(r.get("type") == "LIKES" for r in res.relations)

