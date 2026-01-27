import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class WebSearchService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_s: Optional[float] = None,
        max_results: Optional[int] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.TAVILY_API_KEY
        self.base_url = (base_url if base_url is not None else settings.TAVILY_API_BASE_URL).rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else settings.TAVILY_SEARCH_TIMEOUT_S
        self.max_results = max_results if max_results is not None else settings.TAVILY_MAX_RESULTS
        self._client = client

    def enabled(self) -> bool:
        return bool(settings.WEB_SEARCH_ENABLED and self.api_key)

    async def search(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.enabled():
            return []

        try:
            url = f"{self.base_url}/search"
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results if max_results is not None else self.max_results,
                "include_answer": False,
                "include_raw_content": False,
            }
            if self._client is not None:
                resp = await self._client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            else:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            results = []
            for item in (data.get("results") or [])[: payload["max_results"]]:
                results.append(
                    {
                        "title": item.get("title") or "",
                        "url": item.get("url") or "",
                        "content": item.get("content") or item.get("snippet") or "",
                        "score": item.get("score"),
                        "published_date": item.get("published_date"),
                    }
                )
            return results
        except Exception as e:
            logger.warning(f"Web search failed: {type(e).__name__}: {e}")
            return []

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
