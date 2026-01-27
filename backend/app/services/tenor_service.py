import json
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TenorService:
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.http = httpx.AsyncClient(timeout=settings.MEME_GIF_FETCH_TIMEOUT_MS / 1000.0)

    async def close(self):
        await self.http.aclose()

    async def search_first_gif_url(self, query: str) -> Optional[str]:
        q = (query or "").strip()
        if not q:
            return None
        if (not settings.MEME_GIF_FETCH_ENABLED) or (not settings.TENOR_API_KEY):
            return None

        cache_key = f"tenor:gif:{q.lower()}"
        if self.redis:
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    return cached.decode("utf-8")
            except Exception:
                pass

        try:
            res = await self.http.get(
                f"{settings.TENOR_API_BASE_URL}/search",
                params={
                    "key": settings.TENOR_API_KEY,
                    "client_key": settings.TENOR_CLIENT_KEY,
                    "q": q,
                    "limit": 1,
                    "media_filter": "gif,tinygif",
                },
            )
            res.raise_for_status()
            data = res.json()
            results = data.get("results") or []
            if not results:
                return None
            media = (results[0].get("media_formats") or {})
            for k in ("gif", "tinygif", "mediumgif"):
                fmt = media.get(k) or {}
                url = fmt.get("url")
                if url:
                    if self.redis:
                        try:
                            await self.redis.setex(cache_key, 6 * 3600, url)
                        except Exception:
                            pass
                    return url
            return None
        except Exception as e:
            logger.warning(f"Tenor fetch failed: {e}")
            return None
