"""
Risk Assessment scoring engine. Composite score (0-100) is a weighted
blend of up to four measurable factors:

  1. alert_density   -- recent Alert volume/severity within the profile's
                         monitored radius and categories (from Postgres)
  2. hydration_signal -- volume of hydrated intelligence records in
                         monitored categories that geographically match
                         the profile (from the Redis cache written by the
                         Hydration Engine -- same read path as
                         IntelligenceService)
  3. incident_history -- count of Incidents in the same categories over
                         a trailing 30-day window
  4. correlation_activity -- active CorrelationClusters touching this
                         profile's monitored categories

Each factor is normalized to 0-100 before weighting so the composite score
stays comparable across profiles with very different absolute volumes.
Weights default to equal (25% each) but are overridable per-profile via
`weighting_config`.
"""
from __future__ import annotations

import math
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import CacheManager
from app.db.base import utcnow
from app.exceptions.base import NotFoundError
from app.models.alerts import Alert
from app.models.risk_assessment import RiskProfile, RiskScore, risk_level_from_score
from app.repositories.base import BaseRepository
from app.schemas.risk_assessment import RiskProfileCreate, RiskProfileUpdate

DEFAULT_WEIGHTS = {
    "alert_density": 0.25,
    "hydration_signal": 0.25,
    "incident_history": 0.25,
    "correlation_activity": 0.25,
}
SEVERITY_POINTS = {"critical": 25, "high": 15, "medium": 8, "low": 3, "informational": 1}
EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class RiskProfileRepository(BaseRepository[RiskProfile]):
    model = RiskProfile

    async def list_for_org(self, organization_id: uuid.UUID) -> list[RiskProfile]:
        stmt = (
            select(RiskProfile)
            .where(RiskProfile.organization_id == organization_id, RiskProfile.is_active.is_(True))
            .options(selectinload(RiskProfile.scores))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_with_scores(self, profile_id: uuid.UUID) -> RiskProfile | None:
        stmt = select(RiskProfile).where(RiskProfile.id == profile_id).options(selectinload(RiskProfile.scores))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class RiskAssessmentService:
    def __init__(self, session: AsyncSession, cache: CacheManager) -> None:
        self.session = session
        self.cache = cache
        self.profiles = RiskProfileRepository(session)

    async def list_for_org(self, organization_id: uuid.UUID) -> list[RiskProfile]:
        return await self.profiles.list_for_org(organization_id)

    async def get(self, profile_id: uuid.UUID, organization_id: uuid.UUID) -> RiskProfile:
        profile = await self.profiles.get_with_scores(profile_id)
        if profile is None or profile.organization_id != organization_id:
            raise NotFoundError("Risk profile not found")
        return profile

    async def create(self, organization_id: uuid.UUID, payload: RiskProfileCreate) -> RiskProfile:
        profile = await self.profiles.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            name=payload.name,
            subject_type=payload.subject_type,
            description=payload.description,
            latitude=payload.latitude,
            longitude=payload.longitude,
            monitored_radius_km=payload.monitored_radius_km,
            monitored_categories=payload.monitored_categories,
            weighting_config=payload.weighting_config,
        )
        await self.recalculate(profile.id, organization_id)
        return await self.get(profile.id, organization_id)

    async def update(self, profile_id: uuid.UUID, organization_id: uuid.UUID, payload: RiskProfileUpdate) -> RiskProfile:
        profile = await self.get(profile_id, organization_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(profile, key, value)
        await self.session.flush()
        return profile

    async def delete(self, profile_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        profile = await self.get(profile_id, organization_id)
        profile.is_active = False
        await self.session.flush()

    async def recalculate(self, profile_id: uuid.UUID, organization_id: uuid.UUID) -> RiskScore:
        profile = await self.get(profile_id, organization_id)
        weights = {**DEFAULT_WEIGHTS, **profile.weighting_config}

        alert_density = await self._score_alert_density(profile)
        hydration_signal = await self._score_hydration_signal(profile)
        incident_history = await self._score_incident_history(profile)
        correlation_activity = await self._score_correlation_activity(profile)

        raw_factors = {
            "alert_density": alert_density,
            "hydration_signal": hydration_signal,
            "incident_history": incident_history,
            "correlation_activity": correlation_activity,
        }

        composite = sum(raw_factors[k] * weights.get(k, DEFAULT_WEIGHTS[k]) for k in raw_factors)
        composite = round(min(100.0, max(0.0, composite)), 2)
        level = risk_level_from_score(composite)

        score = RiskScore(
            id=uuid.uuid4(),
            profile_id=profile.id,
            composite_score=composite,
            risk_level=level,
            factor_breakdown={
                "factors": raw_factors,
                "weights": weights,
                "methodology": (
                    "Weighted blend of normalized 0-100 sub-scores: alert density "
                    "(severity-weighted alert volume within monitored radius/categories), "
                    "hydration signal (hydrated intelligence record volume), incident "
                    "history (30-day trailing incident count), and correlation activity "
                    "(active correlation clusters touching monitored categories)."
                ),
            },
            calculated_at=utcnow(),
        )
        self.session.add(score)
        await self.session.flush()

        if level in ("critical", "high"):
            await self.cache.publish(
                f"ws:org:{organization_id}",
                {
                    "type": "risk_score_updated",
                    "profile_id": str(profile.id),
                    "profile_name": profile.name,
                    "composite_score": composite,
                    "risk_level": level,
                },
            )

        return score

    async def _score_alert_density(self, profile: RiskProfile) -> float:
        cutoff = utcnow() - timedelta(days=7)
        stmt = select(Alert).where(Alert.organization_id == profile.organization_id, Alert.created_at >= cutoff)
        if profile.monitored_categories:
            stmt = stmt.where(Alert.category.in_(profile.monitored_categories))
        result = await self.session.execute(stmt)
        alerts = list(result.scalars().all())

        if profile.latitude is not None and profile.longitude is not None and profile.monitored_radius_km:
            alerts = [
                a
                for a in alerts
                if a.latitude is not None
                and a.longitude is not None
                and _haversine_km(profile.latitude, profile.longitude, a.latitude, a.longitude)
                <= profile.monitored_radius_km
            ]

        raw_points = sum(SEVERITY_POINTS.get(a.severity, 3) for a in alerts)
        return min(100.0, raw_points)

    async def _score_hydration_signal(self, profile: RiskProfile) -> float:
        if not profile.monitored_categories:
            return 0.0
        total_records = 0
        for category in profile.monitored_categories:
            keys = await self.cache.keys_by_pattern(f"hydrated:{category}:*")
            for key in keys:
                payload = await self.cache.get_json(key)
                if payload:
                    total_records += payload.get("record_count", 0)
        # Normalize: 50+ combined records across monitored categories -> saturate at 100.
        return min(100.0, (total_records / 50.0) * 100)

    async def _score_incident_history(self, profile: RiskProfile) -> float:
        try:
            from app.models.incident import Incident

            cutoff = utcnow() - timedelta(days=30)
            stmt = select(func.count()).select_from(Incident).where(
                Incident.organization_id == profile.organization_id, Incident.created_at >= cutoff
            )
            if profile.monitored_categories:
                stmt = stmt.where(Incident.category.in_(profile.monitored_categories))
            result = await self.session.execute(stmt)
            count = result.scalar_one()
            
            return min(100.0, (count / 10.0) * 100)
        except Exception:  # noqa: BLE001
            return 0.0

    async def _score_correlation_activity(self, profile: RiskProfile) -> float:
        try:
            from app.models.event_correlation import CorrelationCluster, CorrelationClusterStatus

            stmt = select(func.count()).select_from(CorrelationCluster).where(
                CorrelationCluster.organization_id == profile.organization_id,
                CorrelationCluster.status == CorrelationClusterStatus.ACTIVE.value,
            )
            result = await self.session.execute(stmt)
            count = result.scalar_one()
            # Normalize: 5+ active clusters -> saturate at 100.
            return min(100.0, (count / 5.0) * 100)
        except Exception:  
            return 0.0