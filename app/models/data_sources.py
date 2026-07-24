"""
Data Source & Connector domain models.

A `DataSource` represents one configured external integration (a weather
API, a maritime AIS feed, a news API, etc). Each DataSource is hydrated on
a schedule by a `Connector` implementation (see app.connectors) and the
results are written into `HydrationRun` for auditability plus pushed into
Redis/Postgres for serving. `DataSourceCredential` stores encrypted
connection secrets separately from configuration so they can be rotated
and access-audited independently.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimeStampMixin, UUIDPrimaryKeyMixin


class DataSourceCategory(StrEnum):
    THREAT_INTEL = "threat_intelligence"
    OSINT = "osint"
    SOCMINT = "socmint"
    CYBER = "cyber_intelligence"
    MARITIME = "maritime_intelligence"
    WEATHER = "weather_intelligence"
    FINANCIAL = "financial_intelligence"
    NEWS = "news_intelligence"
    GIS = "gis"
    CUSTOM = "custom"


class DataSourceStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ERROR = "error"


class ConnectorType(StrEnum):
    REST = "rest"
    RSS = "rss"
    WEBSOCKET = "websocket"
    GRAPHQL = "graphql"
    SFTP = "sftp"
    DATABASE = "database"


class HydrationRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DataSource(Base, UUIDPrimaryKeyMixin, TimeStampMixin, SoftDeleteMixin):
    __tablename__ = "data_sources"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    connector_key: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(20), nullable=False, default=ConnectorType.REST.value)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DataSourceStatus.ACTIVE.value)
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sync_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    credentials: Mapped[list["DataSourceCredential"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )
    hydration_runs: Mapped[list["HydrationRun"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_data_sources_category_status", "category", "status"),
        Index("ix_data_sources_org", "organization_id"),
    )

    @property
    def is_circuit_open(self) -> bool:
        from app.db.base import utcnow

        return bool(self.circuit_open_until and self.circuit_open_until > utcnow())


class DataSourceCredential(Base, UUIDPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = "data_source_credentials"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    credential_key: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    data_source: Mapped["DataSource"] = relationship(back_populates="credentials")

    __table_args__ = (Index("ix_ds_credentials_source_key", "data_source_id", "credential_key", unique=True),)


class HydrationRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "hydration_runs"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    data_source: Mapped["DataSource"] = relationship(back_populates="hydration_runs")

    __table_args__ = (Index("ix_hydration_runs_source_started", "data_source_id", "started_at"),)