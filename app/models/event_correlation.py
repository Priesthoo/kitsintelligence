"""
Event Correlation domain model. The Correlation Engine runs periodically
(via Celery beat) over recent Alerts, groups ones that share spatial,
temporal, or categorical proximity into a `CorrelationCluster`, and — when
a cluster crosses a configurable severity/size threshold — auto-escalates
it into an Incident. This is what turns "50 isolated alerts" into "3
correlated situations that need attention."
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin


class CorrelationRuleType(StrEnum):
    SPATIAL_PROXIMITY = "spatial_proximity"
    TEMPORAL_CLUSTERING = "temporal_clustering"
    CATEGORY_MATCH = "category_match"
    ENTITY_OVERLAP = "entity_overlap"


class CorrelationClusterStatus(StrEnum):
    ACTIVE = "active"
    ESCALATED = "escalated"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class CorrelationRule(Base, UUIDPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = "correlation_rules"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    parameters_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    auto_escalate_threshold: Mapped[int] = mapped_column(default=3, nullable=False)
    auto_escalate_severity: Mapped[str] = mapped_column(String(20), default="high", nullable=False)

    __table_args__ = (Index("ix_correlation_rules_org_active", "organization_id", "is_active"),)


class CorrelationCluster(Base, UUIDPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = "correlation_clusters"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("correlation_rules.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CorrelationClusterStatus.ACTIVE.value)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    center_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    center_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_severity: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    escalated_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    members: Mapped[list["CorrelationClusterMember"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_correlation_clusters_org_status", "organization_id", "status"),
    )


class CorrelationClusterMember(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "correlation_cluster_members"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("correlation_clusters.id", ondelete="CASCADE"), nullable=False
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cluster: Mapped["CorrelationCluster"] = relationship(back_populates="members")

    __table_args__ = (Index("ix_correlation_member_unique", "cluster_id", "alert_id", unique=True),)