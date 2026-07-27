"""
Alert domain model. Alerts are the platform's core signal — generated
either by connectors detecting anomalies during hydration (e.g. a threat
feed reporting a new CVE, a maritime feed reporting a vessel entering a
restricted zone) or manually by an analyst. Alerts can be escalated into
Incidents (see app.models.incidents) when they require coordinated
response.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin


class AlertSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertSourceType(StrEnum):
    CONNECTOR = "connector"
    MANUAL = "manual"
    CORRELATION_ENGINE = "correlation_engine"
    RULE_ENGINE = "rule_engine"


class Alert(Base, UUIDPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = "alerts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default=AlertSeverity.MEDIUM.value)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=AlertStatus.OPEN.value)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default=AlertSourceType.MANUAL.value)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_escalated_to_incident: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_alerts_org_status", "organization_id", "status"),
        Index("ix_alerts_org_severity", "organization_id", "severity"),
        Index("ix_alerts_category", "category"),
        Index("ix_alerts_created", "created_at"),
    )