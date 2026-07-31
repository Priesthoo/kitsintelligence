"""DTOs for Analytics, Timeline, and Activity Feed modules."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TrendPoint(BaseModel):
    period: str
    count: int


class AnalyticsSeriesResponse(BaseModel):
    metric: str
    interval: str
    points: list[TrendPoint]


class AnalyticsOverviewResponse(BaseModel):
    generated_at: datetime
    alerts_by_severity: dict[str, int]
    alerts_trend: list[TrendPoint]
    incidents_by_priority: dict[str, int]
    incidents_trend: list[TrendPoint]
    mean_time_to_resolve_hours: float | None
    top_alert_categories: list[dict]


class TimelineEntry(BaseModel):
    id: str
    entry_type: str
    title: str
    description: str | None
    severity_or_priority: str | None
    occurred_at: datetime
    resource_type: str
    resource_id: str


class TimelineResponse(BaseModel):
    entries: list[TimelineEntry]
    total: int


class ActivityFeedEntry(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    created_at: datetime
    metadata_json: dict


class ActivityFeedResponse(BaseModel):
    entries: list[ActivityFeedEntry]
    total: int