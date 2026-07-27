"""DTOs for the Incident Management module."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IncidentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=1)
    category: str
    priority: str = "p3_medium"
    assigned_to_id: uuid.UUID | None = None
    assigned_team_id: uuid.UUID | None = None
    alert_ids: list[uuid.UUID] = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)


class IncidentUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    assigned_to_id: uuid.UUID | None = None
    assigned_team_id: uuid.UUID | None = None


class IncidentAddNote(BaseModel):
    note: str = Field(min_length=1, max_length=5000)
    status_change_to: str | None = None


class IncidentUpdateRead(ORMBase):
    id: uuid.UUID
    author_id: uuid.UUID
    note: str
    status_change_to: str | None
    created_at: datetime


class IncidentRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    description: str
    status: str
    priority: str
    category: str
    assigned_to_id: uuid.UUID | None
    assigned_team_id: uuid.UUID | None
    created_by_id: uuid.UUID
    metadata_json: dict
    resolved_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updates: list[IncidentUpdateRead] = Field(default_factory=list)
    linked_alert_ids: list[uuid.UUID] = Field(default_factory=list)


class IncidentStatsResponse(BaseModel):
    total_open: int
    total_investigating: int
    mean_time_to_resolve_hours: float | None
    by_priority: dict[str, int]