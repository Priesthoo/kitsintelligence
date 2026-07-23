"""Liveness/readiness/health endpoints consumed by Kubernetes probes and uptime monitors."""
from __future__ import annotations

import time

from fastapi import APIRouter, Response, status

from app.core.cache import get_cache_manager
from app.core.config import settings
from app.db.session import check_database_connection

router = APIRouter(tags=["Health"])

_START_TIME = time.time()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.OTEL_SERVICE_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": round(time.time() - _START_TIME, 2),
    }


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict:
    db_ok = await check_database_connection()
    cache = get_cache_manager()
    redis_ok = await cache.ping()

    ready = db_ok and redis_ok
    response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "database": "ok" if db_ok else "unavailable",
            "redis": "ok" if redis_ok else "unavailable",
        },
    }