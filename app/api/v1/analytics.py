"""Analytics, Timeline, and Activity Feed endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permissions
from app.models.identity import User
from app.schemas.analytics import (
    ActivityFeedResponse,
    AnalyticsOverviewResponse,
    AnalyticsSeriesResponse,
    TimelineResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["Analytics"])


@router.get("/analytics/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    user: User = Depends(require_permissions("analytics:read")), db: AsyncSession = Depends(get_db)
) -> dict:
    service = AnalyticsService(db)
    return await service.get_overview(user.organization_id)


@router.get("/analytics/series", response_model=AnalyticsSeriesResponse)
async def get_analytics_series(
    metric: str = Query(..., description="e.g. 'alerts' or 'incidents'"),
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(require_permissions("analytics:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AnalyticsService(db)
    return await service.get_series(user.organization_id, metric, days=days)


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permissions("timeline:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AnalyticsService(db)
    offset = (page - 1) * page_size
    entries, total = await service.get_timeline(user.organization_id, offset=offset, limit=page_size)
    return {"entries": entries, "total": total}


@router.get("/activity-feed", response_model=ActivityFeedResponse)
async def get_activity_feed(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permissions("activity_feed:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AnalyticsService(db)
    offset = (page - 1) * page_size
    entries, total = await service.get_activity_feed(user.organization_id, offset=offset, limit=page_size)
    return {"entries": entries, "total": total}