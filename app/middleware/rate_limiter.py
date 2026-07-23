"""
Sliding-window rate limiter backed by Redis, applied per client (API key,
authenticated user, or IP address as a fallback). Uses a Lua-free approach
via Redis sorted sets: each request adds a timestamped member and prunes
anything outside the window, giving accurate sliding-window semantics
without race conditions across multiple API pod replicas.
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.cache import get_cache_manager
from app.core.config import settings

EXEMPT_PATHS = {"/health", "/health/live", "/health/ready", "/metrics", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        client_id = self._resolve_client_id(request)
        cache = get_cache_manager()
        key = f"ratelimit:{client_id}:{request.url.path}"
        now = time.time()
        window_start = now - settings.RATE_LIMIT_WINDOW_SECONDS

        redis_client = cache._client
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {f"{now}": now})
        pipe.zcard(key)
        pipe.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
        results = await pipe.execute()
        request_count = results[2]

        if request_count > settings.RATE_LIMIT_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Too many requests. Please slow down.",
                        "details": {
                            "limit": settings.RATE_LIMIT_REQUESTS,
                            "window_seconds": settings.RATE_LIMIT_WINDOW_SECONDS,
                        },
                    }
                },
                headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(max(0, settings.RATE_LIMIT_REQUESTS - request_count))
        return response

    @staticmethod
    def _resolve_client_id(request: Request) -> str:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"apikey:{api_key[:16]}"
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return f"token:{hash(auth_header) % (10 ** 12)}"
        forwarded = request.headers.get("X-Forwarded-For")
        client_host = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        return f"ip:{client_host}"