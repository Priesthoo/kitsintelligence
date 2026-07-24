"""DTOs for the Data Sources / Connector Framework admin API."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DataSourceCredentialInput(BaseModel):
    credential_key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1)


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(min_length=2, max_length=150, pattern=r"^[a-z0-9][a-z0-9_-]*[a-z0-9]$")
    category: str
    connector_key: str
    connector_type: str = "rest"
    base_url: str | None = None
    config_json: dict = Field(default_factory=dict)
    sync_interval_seconds: int = Field(default=300, ge=30, le=86400)
    priority: int = Field(default=5, ge=1, le=10)
    is_global: bool = True
    organization_id: uuid.UUID | None = None
    credentials: list[DataSourceCredentialInput] = Field(default_factory=list)


class DataSourceUpdate(BaseModel):
    name: str | None = None
    config_json: dict | None = None
    sync_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    priority: int | None = Field(default=None, ge=1, le=10)
    status: str | None = None
    base_url: str | None = None


class DataSourceRead(ORMBase):
    id: uuid.UUID
    name: str
    slug: str
    category: str
    connector_key: str
    connector_type: str
    base_url: str | None
    status: str
    config_json: dict
    sync_interval_seconds: int
    priority: int
    is_global: bool
    last_synced_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int
    circuit_open_until: datetime | None
    created_at: datetime


class HydrationRunRead(ORMBase):
    id: uuid.UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    records_fetched: int
    records_written: int
    duration_ms: int | None
    error_message: str | None


class ConnectorCatalogEntry(BaseModel):
    key: str