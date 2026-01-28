from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class ApiVersionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, default_version: str = "v1"):
        super().__init__(app)
        self.default_version = default_version

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        version = self.default_version
        path = request.url.path or ""
        if path.startswith("/api/v1/"):
            version = "v1"
        elif path.startswith("/api/v2/"):
            version = "v2"
        response.headers["X-API-Version"] = version
        return response

