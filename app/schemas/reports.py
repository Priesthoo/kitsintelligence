"""DTOs for the Reports module."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReportRequestCreate(BaseModel):
    report_type: str = Field(min_length=2, max_length=100)
    format: str = "pdf"
    parameters_json: dict = Field(default_factory=dict)


class ReportRead(ORMBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    requested_by_id: uuid.UUID
    report_type: str
    format: str
    status: str
    parameters_json: dict
    file_size_bytes: int | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ReportWithDownloadUrl(ReportRead):
    download_url: str | None = None


class ReportTypeInfo(BaseModel):
    report_type: str
    description: str
    supported_formats: list[str]