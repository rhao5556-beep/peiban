import json

import httpx
import pytest

from app.core.config import settings
from app.services.conversation_service import ConversationService
from app.services.web_search_service import WebSearchService


@pytest.mark.asyncio
async def test_web_search_service_parses_results():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["api_key"] == "test-key"
        assert payload["query"] == "RAG 是什么？"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com",
                        "content": "Retrieval-Augmented Generation (RAG) ...",
                        "score": 0.9,
                    }
                ]
            },
        )

    old_enabled = settings.WEB_SEARCH_ENABLED
    old_key = settings.TAVILY_API_KEY
    settings.WEB_SEARCH_ENABLED = True
    settings.TAVILY_API_KEY = "test-key"

    service = WebSearchService(api_key="test-key", base_url="https://api.tavily.com", timeout_s=1.0)
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=1.0)

    try:
        results = await service.search("RAG 是什么？", max_results=3)
        assert len(results) == 1
        assert results[0]["title"] == "Example"
        assert results[0]["url"] == "https://example.com"
        assert "RAG" in results[0]["content"]
    finally:
        await service.aclose()
        settings.WEB_SEARCH_ENABLED = old_enabled
        settings.TAVILY_API_KEY = old_key


def test_should_web_search_heuristics():
    class DummyWebSearch:
        def enabled(self) -> bool:
            return True

    service = ConversationService(
        affinity_service=object(),
        retrieval_service=object(),
        graph_service=object(),
        transaction_manager=object(),
        idempotency_checker=object(),
        working_memory_service=object(),
        response_cache_service=object(),
        web_search_service=DummyWebSearch(),
    )

    assert service._should_web_search("RAG 是什么？") is True
    assert service._should_web_search("你还记得我刚才说了什么吗？") is False


def test_prompt_includes_web_section_when_provided():
    class DummyWebSearch:
        def enabled(self) -> bool:
            return False

    service = ConversationService(
        affinity_service=object(),
        retrieval_service=object(),
        graph_service=object(),
        transaction_manager=object(),
        idempotency_checker=object(),
        working_memory_service=object(),
        response_cache_service=object(),
        web_search_service=DummyWebSearch(),
    )

    affinity = type("Affinity", (), {"new_score": 0.5, "state": "acquaintance"})()
    prompt = service._build_prompt(
        message="RAG 是什么？",
        memories=[],
        affinity=affinity,
        emotion={"primary_emotion": "neutral", "valence": 0.0},
        entity_facts=[],
        conversation_history=[],
        mode="hybrid",
        web_search_results=[{"title": "Example", "url": "https://example.com", "content": "RAG ..."}],
    )

    assert "联网搜索结果" in prompt
    assert "https://example.com" in prompt
