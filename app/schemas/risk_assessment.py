"""DTOs for the Risk Assessment module."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RiskProfileCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    subject_type: str
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    monitored_radius_km: float | None = Field(default=None, gt=0)
    monitored_categories: list[str] = Field(default_factory=list)
    weighting_config: dict = Field(default_factory=dict)


class RiskProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    monitored_radius_km: float | None = Field(default=None, gt=0)
    monitored_categories: list[str] | None = None
    weighting_config: dict | None = None
    is_active: bool | None = None


class RiskScoreRead(ORMBase):
    id: uuid.UUID
    composite_score: float
    risk_level: str
    factor_breakdown: dict
    calculated_at: datetime


class RiskProfileRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    subject_type: str
    description: str | None
    latitude: float | None
    longitude: float | None
    monitored_radius_km: float | None
    monitored_categories: list[str]
    is_active: bool
    created_at: datetime
    latest_score: RiskScoreRead | None = None


class RiskProfileDetail(RiskProfileRead):
    score_history: list[RiskScoreRead] = Field(default_factory=list)


class RecalculateResponse(BaseModel):
    profile_id: uuid.UUID
    composite_score: float
    risk_level: str
    factor_breakdown: dict