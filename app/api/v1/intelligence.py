
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_db, require_permissions
from app.core.cache import CacheManager
from app.models.identity import User
from app.models.data_sources import DataSourceCategory
from app.schemas.intelligence import (
    IntelligenceFeedResponse,
    IntelligenceSummaryResponse,
    OperationalMapResponse,
)
from app.services.intelligence_service import IntelligenceService

router = APIRouter(tags=["Intelligence"])

_CATEGORY_ROUTES: dict[str, tuple[str, str]] = {
    DataSourceCategory.THREAT_INTEL.value: ("threat-intelligence", "threat_intelligence"),
    DataSourceCategory.OSINT.value: ("osint", "osint"),
    DataSourceCategory.SOCMINT.value: ("socmint", "socmint"),
    DataSourceCategory.CYBER.value: ("cyber-intelligence", "cyber_intelligence"),
    DataSourceCategory.MARITIME.value: ("maritime-intelligence", "maritime_intelligence"),
    DataSourceCategory.WEATHER.value: ("weather-intelligence", "weather_intelligence"),
    DataSourceCategory.FINANCIAL.value: ("financial-intelligence", "financial_intelligence"),
    DataSourceCategory.NEWS.value: ("news-intelligence", "news_intelligence"),
}


def _register_category_routes(category_value: str, url_prefix: str, permission_resource: str) -> None:
    @router.get(
        f"/{url_prefix}/feed",
        response_model=IntelligenceFeedResponse,
        name=f"get_{permission_resource}_feed",
    )
    async def get_feed(
        limit_per_source: int = Query(default=100, ge=1, le=500),
        user: User = Depends(require_permissions(f"{permission_resource}:read")),
        db: AsyncSession = Depends(get_db),
        cache: CacheManager = Depends(get_cache),
    ) -> dict:
        service = IntelligenceService(db, cache)
        return await service.get_feed(category_value, user.organization_id, limit_per_source=limit_per_source)

    @router.get(
        f"/{url_prefix}/summary",
        response_model=IntelligenceSummaryResponse,
        name=f"get_{permission_resource}_summary",
    )
    async def get_summary(
        user: User = Depends(require_permissions(f"{permission_resource}:read")),
        db: AsyncSession = Depends(get_db),
        cache: CacheManager = Depends(get_cache),
    ) -> dict:
        service = IntelligenceService(db, cache)
        return await service.get_summary(category_value, user.organization_id)


for _category_value, (_url_prefix, _permission_resource) in _CATEGORY_ROUTES.items():
    _register_category_routes(_category_value, _url_prefix, _permission_resource)


# --------------------------------------------------------------------- #
# GIS / Operational Map (spatially unions every category's hydrated data)
# --------------------------------------------------------------------- #
@router.get("/gis/operational-map", response_model=OperationalMapResponse)
async def get_operational_map(
    categories: list[str] | None = Query(default=None),
    user: User = Depends(require_permissions("gis:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = IntelligenceService(db, cache)
    return await service.get_operational_map(user.organization_id, categories=categories)