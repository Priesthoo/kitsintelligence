"""DTOs for the Alerts module."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AlertCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=1)
    category: str
    severity: str = "medium"
    latitude: float | None = None
    longitude: float | None = None
    metadata_json: dict = Field(default_factory=dict)


class AlertUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    severity: str | None = None
    status: str | None = None


class AlertResolve(BaseModel):
    resolution_notes: str = Field(min_length=1, max_length=2000)


class AlertRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    description: str
    category: str
    severity: str
    status: str
    source_type: str
    source_reference: str | None
    data_source_id: uuid.UUID | None
    latitude: float | None
    longitude: float | None
    metadata_json: dict
    acknowledged_by_id: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_by_id: uuid.UUID | None
    resolved_at: datetime | None
    resolution_notes: str | None
    is_escalated_to_incident: bool
    created_at: datetime


class AlertStatsResponse(BaseModel):
    total_open: int
    total_acknowledged: int
    total_resolved_last_7d: int
    by_severity: dict[str, int]
    by_category: dict[str, int]