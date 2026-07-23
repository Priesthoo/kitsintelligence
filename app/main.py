"""
Application entrypoint. Wires together configuration, logging, tracing,
middleware (request context, rate limiting, CORS, Prometheus), exception
handlers, and the versioned API router, and manages startup/shutdown of
shared resources (DB engine, Redis pool) via the lifespan context.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.cache import get_cache_manager
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.metrics import PrometheusMiddleware, metrics_endpoint
from app.db.session import engine
from app.middleware.exception_handler import register_exception_handlers
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application.startup", version=settings.APP_VERSION, environment=settings.ENVIRONMENT)
    cache = get_cache_manager()
    redis_ok = await cache.ping()
    logger.info("redis.connection_check", ok=redis_ok)
    yield
    logger.info("application.shutdown")
    await cache.close()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="kit Intelligence Platform Backend API",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        default_response_class=JSONResponse,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.add_api_route(settings.PROMETHEUS_METRICS_PATH, metrics_endpoint, include_in_schema=False)

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        from app.core.tracer import configure_tracing

        configure_tracing(app)

    return app


app = create_app()