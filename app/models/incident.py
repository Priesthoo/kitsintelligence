"""
Incident domain model. An Incident is an escalated, coordinated response
effort — typically created from one or more Alerts that together
represent a single operational event requiring assignment, tracking, and
resolution. Incidents carry their own timeline (via IncidentUpdate) so the
full response history is auditable independent of the underlying alerts.

`created_by_id` is nullable to support system-generated incidents (e.g.
auto-escalation from the Event Correlation Engine, which has no human
actor); `is_system_generated` distinguishes these for UI/audit purposes.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentPriority(StrEnum):
    P1_CRITICAL = "p1_critical"
    P2_HIGH = "p2_high"
    P3_MEDIUM = "p3_medium"
    P4_LOW = "p4_low"


class Incident(Base, UUIDPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = "incidents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=IncidentStatus.OPEN.value)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default=IncidentPriority.P3_MEDIUM.value)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_system_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    updates: Mapped[list["IncidentUpdate"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="IncidentUpdate.created_at"
    )
    linked_alerts: Mapped[list["IncidentAlertLink"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_incidents_org_status", "organization_id", "status"),
        Index("ix_incidents_org_priority", "organization_id", "priority"),
        Index("ix_incidents_assigned", "assigned_to_id"),
    )


class IncidentUpdate(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incident_updates"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    status_change_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    incident: Mapped["Incident"] = relationship(back_populates="updates")

    __table_args__ = (Index("ix_incident_updates_incident", "incident_id", "created_at"),)


class IncidentAlertLink(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incident_alert_links"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    incident: Mapped["Incident"] = relationship(back_populates="linked_alerts")

    __table_args__ = (Index("ix_incident_alert_link_unique", "incident_id", "alert_id", unique=True),)