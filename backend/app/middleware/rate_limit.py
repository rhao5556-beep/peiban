"""Rate Limiting 中间件"""
import time
from typing import Callable, Dict, Tuple, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于 IP 的速率限制中间件"""
    
    def __init__(self, app, requests_per_minute: int = 100, redis_client=None, max_fallback_keys: int = 10000):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._redis = redis_client
        self._fallback: Dict[str, Tuple[int, float]] = {}
        self._max_fallback_keys = max_fallback_keys

    def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            from app.core.database import get_redis_client
            self._redis = get_redis_client()
        except Exception:
            self._redis = None
        return self._redis

    def _bucket_key(self, client_ip: str, now: float) -> str:
        bucket = int(now // 60)
        return f"ratelimit:{client_ip}:{bucket}"

    def _fallback_incr(self, key: str, now: float) -> int:
        count, expires_at = self._fallback.get(key, (0, 0.0))
        if expires_at and now >= expires_at:
            count = 0
            expires_at = 0.0
        if not expires_at:
            expires_at = (int(now // 60) + 1) * 60 + 1
        count += 1
        self._fallback[key] = (count, expires_at)
        if len(self._fallback) > self._max_fallback_keys:
            cutoff = now - 120
            keys = list(self._fallback.keys())
            for k in keys[: min(len(keys), 500)]:
                _, exp = self._fallback.get(k, (0, 0.0))
                if exp and exp < cutoff:
                    self._fallback.pop(k, None)
        return count
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过健康检查和文档端点
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # 获取客户端 IP
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()
        key = self._bucket_key(client_ip, current_time)

        redis = self._get_redis()
        count: Optional[int] = None
        if redis:
            try:
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, 61)
            except Exception:
                count = None

        if count is None:
            count = self._fallback_incr(key, current_time)

        if count > self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "message": f"Too many requests. Limit: {self.requests_per_minute}/minute",
                    "retry_after": 60
                },
                headers={"Retry-After": "60"}
            )

        response = await call_next(request)
        remaining = max(0, self.requests_per_minute - int(count))
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
        return response
