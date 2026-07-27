"""
Shared DTOs for every intelligence category (Threat Intel, OSINT, SOCMINT,
Cyber, Maritime, Weather, Financial, News, GIS). All of these read from the
same hydration cache structure written by the Hydration Engine, so one
schema set serves all eight categories.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IntelligenceRecord(BaseModel):
    source_slug: str
    category: str
    hydrated_at: datetime
    data: dict[str, Any]


class IntelligenceFeedResponse(BaseModel):
    category: str
    sources_hydrated: int
    sources_stale_or_missing: int
    total_records: int
    records: list[IntelligenceRecord]


class IntelligenceSourceSummary(BaseModel):
    source_slug: str
    status: str
    last_synced_at: datetime | None
    last_success_at: datetime | None
    record_count: int
    is_stale: bool


class IntelligenceSummaryResponse(BaseModel):
    category: str
    sources: list[IntelligenceSourceSummary]


class GeoFeature(BaseModel):
    source_slug: str
    name: str | None = None
    latitude: float
    longitude: float
    category: str
    properties: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime | None = None


class OperationalMapResponse(BaseModel):
    feature_count: int
    features: list[GeoFeature]
    categories_included: list[str] 