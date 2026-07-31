"""DTOs for the Notifications module."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NotificationRead(ORMBase):
    id: uuid.UUID
    category: str
    channel: str
    status: str
    title: str
    body: str
    metadata_json: dict
    is_read: bool
    read_at: datetime | None
    sent_at: datetime | None
    scheduled_for: datetime | None
    created_at: datetime


class NotificationPreferenceRead(ORMBase):
    id: uuid.UUID
    category: str
    channel: str
    is_enabled: bool


class NotificationPreferenceUpdate(BaseModel):
    category: str
    channel: str
    is_enabled: bool


class NotificationStatsResponse(BaseModel):
    unread_count: int
    total_count: int


class BulkMarkReadRequest(BaseModel):
    notification_ids: list[uuid.UUID] = Field(default_factory=list)
    mark_all: bool = False