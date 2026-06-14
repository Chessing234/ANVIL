"""HTTP middleware: structured logging, CORS, rate limiting."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Awaitable, Callable

import structlog
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = structlog.get_logger("api.http")

_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_THREAD_LOCK = threading.Lock()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit structured JSON logs with request duration."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client=request.client.host if request.client else None,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter (default 100 requests/minute per client IP)."""

    def __init__(self, app: ASGIApp, requests_per_minute: int) -> None:
        super().__init__(app)
        self._limit = max(1, requests_per_minute)
        self._window = 60.0

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/redoc"):
            return await call_next(request)
        if path == "/api/v1/system/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            client_ip = fwd.split(",")[0].strip()

        now = time.monotonic()
        with _RATE_THREAD_LOCK:
            bucket = _RATE_BUCKETS[client_ip]
            while bucket and now - bucket[0] > self._window:
                bucket.popleft()
            if len(bucket) >= self._limit:
                from starlette.responses import JSONResponse
                from datetime import datetime, timezone

                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "detail": f"Maximum {self._limit} requests per minute for this client.",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            bucket.append(now)
        return await call_next(request)
