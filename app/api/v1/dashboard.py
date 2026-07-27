"""Dashboard and System Status endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_db, require_permissions
from app.core.cache import CacheManager
from app.models.identity import User
from app.schemas.dashboard import DashboardResponse, SystemStatusResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    user: User = Depends(require_permissions("dashboard:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = DashboardService(db, cache)
    return await service.get_dashboard(user)


@router.get("/system-status", response_model=SystemStatusResponse)
async def get_system_status(
    _: User = Depends(require_permissions("system_status:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = DashboardService(db, cache)
    return await service.get_system_status()