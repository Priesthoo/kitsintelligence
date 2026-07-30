"""DTOs for the Event Correlation module."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CorrelationRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    rule_type: str
    parameters_json: dict = Field(default_factory=dict)
    auto_escalate_threshold: int = Field(default=3, ge=2, le=100)
    auto_escalate_severity: str = "high"


class CorrelationRuleUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    parameters_json: dict | None = None
    auto_escalate_threshold: int | None = Field(default=None, ge=2, le=100)
    auto_escalate_severity: str | None = None


class CorrelationRuleRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    name: str
    rule_type: str
    is_active: bool
    parameters_json: dict
    auto_escalate_threshold: int
    auto_escalate_severity: str


class CorrelationClusterRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    rule_id: uuid.UUID
    status: str
    summary: str
    center_latitude: float | None
    center_longitude: float | None
    alert_count: int
    max_severity: str
    escalated_incident_id: uuid.UUID | None
    created_at: datetime
    member_alert_ids: list[uuid.UUID] = Field(default_factory=list)


class RunCorrelationPassResponse(BaseModel):
    alerts_scanned: int
    clusters_created: int