"""DTOs for Dashboard and System Status."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CategoryHealthSummary(BaseModel):
    category: str
    total_sources: int
    healthy_sources: int
    stale_sources: int
    error_sources: int
    total_records: int


class DashboardResponse(BaseModel):
    generated_at: datetime
    organization_name: str
    active_users: int
    total_alerts_last_24h: int
    open_incidents: int
    category_health: list[CategoryHealthSummary]
    recent_activity_count: int


class SystemComponentStatus(BaseModel):
    name: str
    status: str
    detail: str | None = None


class SystemStatusResponse(BaseModel):
    generated_at: datetime
    overall_status: str
    components: list[SystemComponentStatus]
    active_data_sources: int
    circuit_breakers_open: int
    hydration_jobs_last_hour: int
    websocket_connections: int