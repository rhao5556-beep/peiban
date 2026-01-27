"""Rate Limiting 中间件"""
import time
from collections import defaultdict
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于 IP 的速率限制中间件"""
    
    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过健康检查和文档端点
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # 获取客户端 IP
        client_ip = request.client.host if request.client else "unknown"
        
        # 清理过期请求记录
        current_time = time.time()
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if current_time - req_time < 60
        ]
        
        # 检查速率限制
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "message": f"Too many requests. Limit: {self.requests_per_minute}/minute",
                    "retry_after": 60
                },
                headers={"Retry-After": "60"}
            )
        
        # 记录请求
        self.requests[client_ip].append(current_time)
        
        # 添加速率限制头
        response = await call_next(request)
        remaining = self.requests_per_minute - len(self.requests[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
        return response
