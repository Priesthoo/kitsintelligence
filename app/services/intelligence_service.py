"""
Intelligence read service: the single place every Intelligence-category API
(threat intel, OSINT, SOCMINT, cyber, maritime, weather, financial, news,
GIS) goes to fetch data. It never talks to an external API directly -- it
only reads what the Hydration Engine already wrote to Redis, which is what
guarantees these endpoints respond in single-digit milliseconds regardless
of upstream API latency or downtime.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.cache import CacheManager
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.data_sources import DataSource, DataSourceCategory
from app.repositories.data_sources import DataSourceAdminRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

CACHE_KEY_PREFIX = "hydrated"
STALE_THRESHOLD_MULTIPLIER = 3  # a source is "stale" if now - last_hydrated > sync_interval * this


class IntelligenceService:
    def __init__(self, session: AsyncSession, cache: CacheManager) -> None:
        self.session = session
        self.cache = cache
        self.sources = DataSourceAdminRepository(session)

    async def _sources_for_category(self, category: str, organization_id) -> list[DataSource]:  # noqa: ANN001
        all_sources = await self.sources.list_visible_to_org(organization_id)
        return [s for s in all_sources if s.category == category and not s.is_deleted]

    async def get_feed(self, category: str, organization_id, *, limit_per_source: int = 100) -> dict:  # noqa: ANN001
        sources = await self._sources_for_category(category, organization_id)
        records: list[dict] = []
        hydrated_count = 0
        missing_count = 0

        for source in sources:
            cache_key = f"{CACHE_KEY_PREFIX}:{category}:{source.slug}"
            payload = await self.cache.get_json(cache_key)
            if payload is None:
                missing_count += 1
                continue
            hydrated_count += 1
            for record in payload.get("records", [])[:limit_per_source]:
                records.append(
                    {
                        "source_slug": source.slug,
                        "category": category,
                        "hydrated_at": payload.get("hydrated_at"),
                        "data": record,
                    }
                )

        return {
            "category": category,
            "sources_hydrated": hydrated_count,
            "sources_stale_or_missing": missing_count,
            "total_records": len(records),
            "records": records,
        }

    async def get_summary(self, category: str, organization_id) -> dict:  # noqa: ANN001
        sources = await self._sources_for_category(category, organization_id)
        summaries = []
        now = utcnow()

        for source in sources:
            cache_key = f"{CACHE_KEY_PREFIX}:{category}:{source.slug}"
            payload = await self.cache.get_json(cache_key)
            record_count = payload.get("record_count", 0) if payload else 0

            is_stale = True
            if source.last_success_at:
                elapsed = (now - source.last_success_at).total_seconds()
                is_stale = elapsed > (source.sync_interval_seconds * STALE_THRESHOLD_MULTIPLIER)

            summaries.append(
                {
                    "source_slug": source.slug,
                    "status": source.status,
                    "last_synced_at": source.last_synced_at,
                    "last_success_at": source.last_success_at,
                    "record_count": record_count,
                    "is_stale": is_stale,
                }
            )

        return {"category": category, "sources": summaries}

    async def get_operational_map(
        self, organization_id, *, categories: list[str] | None = None  # noqa: ANN001
    ) -> dict:
        target_categories = categories or [c.value for c in DataSourceCategory if c != DataSourceCategory.CUSTOM]
        features: list[dict] = []

        for category in target_categories:
            feed = await self.get_feed(category, organization_id, limit_per_source=200)
            for record in feed["records"]:
                data = record["data"]
                lat = data.get("latitude") or data.get("lat")
                lon = data.get("longitude") or data.get("lon")
                if lat is None or lon is None:
                    continue
                features.append(
                    {
                        "source_slug": record["source_slug"],
                        "name": data.get("location_name") or data.get("name"),
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "category": category,
                        "properties": {k: v for k, v in data.items() if k not in {"latitude", "longitude", "lat", "lon"}},
                        "observed_at": data.get("observed_at"),
                    }
                )

        return {
            "feature_count": len(features),
            "features": features,
            "categories_included": target_categories,
        }