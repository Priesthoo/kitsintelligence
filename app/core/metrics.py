"""Prometheus metrics: HTTP request counters/histograms plus domain-level gauges."""
from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status_code"]
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "path"]
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress", "In-flight HTTP requests", ["method", "path"]
)
HYDRATION_JOBS_TOTAL = Counter(
    "hydration_jobs_total", "Total data-source hydration jobs executed", ["source", "status"]
)
HYDRATION_JOB_DURATION_SECONDS = Histogram(
    "hydration_job_duration_seconds", "Hydration job execution time", ["source"]
)
CONNECTOR_REQUESTS_TOTAL = Counter(
    "connector_requests_total", "Total external connector calls", ["connector", "status"]
)
WEBSOCKET_CONNECTIONS_ACTIVE = Gauge(
    "websocket_connections_active", "Currently active WebSocket connections"
)
ALERTS_GENERATED_TOTAL = Counter(
    "alerts_generated_total", "Total alerts generated", ["severity", "category"]
)
CACHE_HIT_TOTAL = Counter("cache_hit_total", "Cache hits", ["cache_key_prefix"])
CACHE_MISS_TOTAL = Counter("cache_miss_total", "Cache misses", ["cache_key_prefix"])


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, path=path).inc()
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, path=path).dec()
        duration = time.perf_counter() - start
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration)
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=response.status_code).inc()
        return response


def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)