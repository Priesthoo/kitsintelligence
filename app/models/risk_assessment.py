"""
Risk Assessment domain model. Unlike Alerts (event-driven, point-in-time)
and Incidents (response-tracking), a RiskAssessment is a standing,
periodically-recalculated score for a defined subject (a region, an asset,
a route, an entity) that aggregates signal from multiple intelligence
categories into a single composite risk figure with a documented
methodology, so analysts can see *why* a score is what it is.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin


class RiskSubjectType(StrEnum):
    REGION = "region"
    ASSET = "asset"
    ROUTE = "route"
    ENTITY = "entity"
    FACILITY = "facility"


class RiskLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    MINIMAL = "minimal"


def risk_level_from_score(score: float) -> str:
    if score >= 80:
        return RiskLevel.CRITICAL.value
    if score >= 60:
        return RiskLevel.HIGH.value
    if score >= 40:
        return RiskLevel.MODERATE.value
    if score >= 20:
        return RiskLevel.LOW.value
    return RiskLevel.MINIMAL.value


class RiskProfile(Base, UUIDPrimaryKeyMixin, TimeStampMixin):
    """A subject being tracked for risk (e.g. 'Lagos Port Complex', 'Gulf of Guinea Shipping Lane')."""

    __tablename__ = "risk_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    monitored_radius_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    monitored_categories: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    weighting_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    scores: Mapped[list["RiskScore"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="RiskScore.calculated_at.desc()"
    )

    __table_args__ = (Index("ix_risk_profiles_org", "organization_id", "is_active"),)


class RiskScore(Base, UUIDPrimaryKeyMixin):
    """A single point-in-time calculation for a RiskProfile, with full factor breakdown for explainability."""

    __tablename__ = "risk_scores"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_profiles.id", ondelete="CASCADE"), nullable=False
    )
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    factor_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    profile: Mapped["RiskProfile"] = relationship(back_populates="scores")

    __table_args__ = (Index("ix_risk_scores_profile_calculated", "profile_id", "calculated_at"),)