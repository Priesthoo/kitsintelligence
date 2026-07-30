"""
Event Correlation Engine. Runs over recent uncorrelated alerts and applies
active CorrelationRules to group related ones. Implements two rule types
concretely (spatial proximity via haversine distance, temporal clustering
via a sliding time window); category_match and entity_overlap follow the
same pluggable pattern and can be added without touching the orchestration
logic in `run_correlation_pass`.
"""
from __future__ import annotations

import math
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import CacheManager
from app.db.base import utcnow
from app.exceptions.base import NotFoundError
from app.models.alerts import Alert, AlertSourceType
from app.models.event_correlation import (
    CorrelationCluster,
    CorrelationClusterMember,
    CorrelationClusterStatus,
    CorrelationRule,
    CorrelationRuleType,
)
from app.repositories.base import BaseRepository
from app.services.audit_service import AuditService

SEVERITY_RANK = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class CorrelationRuleRepository(BaseRepository[CorrelationRule]):
    model = CorrelationRule

    async def list_active_for_org(self, organization_id: uuid.UUID) -> list[CorrelationRule]:
        stmt = select(CorrelationRule).where(
            CorrelationRule.is_active.is_(True),
            (CorrelationRule.organization_id.is_(None)) | (CorrelationRule.organization_id == organization_id),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class CorrelationClusterRepository(BaseRepository[CorrelationCluster]):
    model = CorrelationCluster

    async def get_with_members(self, cluster_id: uuid.UUID) -> CorrelationCluster | None:
        stmt = (
            select(CorrelationCluster)
            .where(CorrelationCluster.id == cluster_id)
            .options(selectinload(CorrelationCluster.members))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_for_org(self, organization_id: uuid.UUID) -> list[CorrelationCluster]:
        stmt = (
            select(CorrelationCluster)
            .where(
                CorrelationCluster.organization_id == organization_id,
                CorrelationCluster.status == CorrelationClusterStatus.ACTIVE.value,
            )
            .options(selectinload(CorrelationCluster.members))
            .order_by(CorrelationCluster.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())


class CorrelationService:
    def __init__(self, session: AsyncSession, cache: CacheManager) -> None:
        self.session = session
        self.cache = cache
        self.rules = CorrelationRuleRepository(session)
        self.clusters = CorrelationClusterRepository(session)
        self.audit = AuditService(session)

    async def run_correlation_pass(self, organization_id: uuid.UUID, *, lookback_minutes: int = 60) -> dict:
        cutoff = utcnow() - timedelta(minutes=lookback_minutes)

        # Only correlate alerts not already claimed by an active cluster this pass.
        already_clustered_stmt = select(CorrelationClusterMember.alert_id).join(CorrelationCluster).where(
            CorrelationCluster.organization_id == organization_id,
            CorrelationCluster.status == CorrelationClusterStatus.ACTIVE.value,
        )
        already_clustered_result = await self.session.execute(already_clustered_stmt)
        already_clustered_ids = {row[0] for row in already_clustered_result.all()}

        recent_alerts_stmt = select(Alert).where(
            Alert.organization_id == organization_id,
            Alert.created_at >= cutoff,
            Alert.status != "dismissed",
        )
        recent_result = await self.session.execute(recent_alerts_stmt)
        recent_alerts = [a for a in recent_result.scalars().all() if a.id not in already_clustered_ids]

        active_rules = await self.rules.list_active_for_org(organization_id)
        clusters_created = 0

        for rule in active_rules:
            if rule.rule_type == CorrelationRuleType.SPATIAL_PROXIMITY.value:
                clusters_created += await self._apply_spatial_rule(organization_id, rule, recent_alerts)
            elif rule.rule_type == CorrelationRuleType.TEMPORAL_CLUSTERING.value:
                clusters_created += await self._apply_temporal_rule(organization_id, rule, recent_alerts)
            elif rule.rule_type == CorrelationRuleType.CATEGORY_MATCH.value:
                clusters_created += await self._apply_category_rule(organization_id, rule, recent_alerts)

        return {"alerts_scanned": len(recent_alerts), "clusters_created": clusters_created}

    async def _apply_spatial_rule(self, organization_id: uuid.UUID, rule: CorrelationRule, alerts: list[Alert]) -> int:
        radius_km = rule.parameters_json.get("radius_km", 10.0)
        geo_alerts = [a for a in alerts if a.latitude is not None and a.longitude is not None]
        used: set[uuid.UUID] = set()
        created = 0

        for anchor in geo_alerts:
            if anchor.id in used:
                continue
            group = [anchor]
            for other in geo_alerts:
                if other.id == anchor.id or other.id in used:
                    continue
                if _haversine_km(anchor.latitude, anchor.longitude, other.latitude, other.longitude) <= radius_km:
                    group.append(other)

            if len(group) >= rule.auto_escalate_threshold:
                await self._create_cluster(organization_id, rule, group, "Spatial proximity cluster")
                used.update(a.id for a in group)
                created += 1
        return created

    async def _apply_temporal_rule(self, organization_id: uuid.UUID, rule: CorrelationRule, alerts: list[Alert]) -> int:
        window_minutes = rule.parameters_json.get("window_minutes", 15)
        category_filter = rule.parameters_json.get("category")
        candidates = [a for a in alerts if category_filter is None or a.category == category_filter]
        candidates.sort(key=lambda a: a.created_at)

        created = 0
        used: set[uuid.UUID] = set()
        for i, anchor in enumerate(candidates):
            if anchor.id in used:
                continue
            group = [anchor]
            for other in candidates[i + 1 :]:
                if other.id in used:
                    continue
                if (other.created_at - anchor.created_at).total_seconds() <= window_minutes * 60:
                    group.append(other)
                else:
                    break

            if len(group) >= rule.auto_escalate_threshold:
                await self._create_cluster(organization_id, rule, group, "Temporal clustering (burst detected)")
                used.update(a.id for a in group)
                created += 1
        return created

    async def _apply_category_rule(self, organization_id: uuid.UUID, rule: CorrelationRule, alerts: list[Alert]) -> int:
        by_category: dict[str, list[Alert]] = {}
        for a in alerts:
            by_category.setdefault(a.category, []).append(a)

        created = 0
        for category, group in by_category.items():
            if len(group) >= rule.auto_escalate_threshold:
                await self._create_cluster(organization_id, rule, group, f"Repeated '{category}' alerts")
                created += 1
        return created

    async def _create_cluster(
        self, organization_id: uuid.UUID, rule: CorrelationRule, alerts: list[Alert], summary: str
    ) -> CorrelationCluster:
        geo_alerts = [a for a in alerts if a.latitude is not None and a.longitude is not None]
        center_lat = sum(a.latitude for a in geo_alerts) / len(geo_alerts) if geo_alerts else None
        center_lon = sum(a.longitude for a in geo_alerts) / len(geo_alerts) if geo_alerts else None
        max_severity = max((a.severity for a in alerts), key=lambda s: SEVERITY_RANK.get(s, 0))

        cluster = await self.clusters.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            rule_id=rule.id,
            status=CorrelationClusterStatus.ACTIVE.value,
            summary=f"{summary}: {len(alerts)} related alerts",
            center_latitude=center_lat,
            center_longitude=center_lon,
            alert_count=len(alerts),
            max_severity=max_severity,
            metadata_json={"rule_type": rule.rule_type},
        )

        for alert in alerts:
            self.session.add(
                CorrelationClusterMember(id=uuid.uuid4(), cluster_id=cluster.id, alert_id=alert.id, added_at=utcnow())
            )
        await self.session.flush()

        await self.cache.publish(
            f"ws:org:{organization_id}",
            {
                "type": "correlation_cluster_created",
                "cluster_id": str(cluster.id),
                "summary": cluster.summary,
                "alert_count": cluster.alert_count,
                "max_severity": cluster.max_severity,
            },
        )

        if SEVERITY_RANK.get(max_severity, 0) >= SEVERITY_RANK.get(rule.auto_escalate_severity, 3):
            await self._auto_escalate(cluster, alerts)

        return cluster

    async def _auto_escalate(self, cluster: CorrelationCluster, alerts: list[Alert]) -> None:
        from app.models.incident import Incident, IncidentAlertLink, IncidentPriority, IncidentStatus

        priority_map = {"critical": IncidentPriority.P1_CRITICAL, "high": IncidentPriority.P2_HIGH}
        priority = priority_map.get(cluster.max_severity, IncidentPriority.P3_MEDIUM).value

        incident = Incident(
            id=uuid.uuid4(),
            organization_id=cluster.organization_id,
            title=cluster.summary,
            description=(
                f"Auto-escalated by the Event Correlation Engine from {len(alerts)} correlated alerts. "
                f"Rule: {cluster.metadata_json.get('rule_type')}."
            ),
            status=IncidentStatus.OPEN.value,
            priority=priority,
            category=alerts[0].category if alerts else "correlated",
            created_by_id=None,
            is_system_generated=True,
            metadata_json={"correlation_cluster_id": str(cluster.id)},
        )
        self.session.add(incident)
        await self.session.flush()

        for alert in alerts:
            alert.is_escalated_to_incident = True
            self.session.add(
                IncidentAlertLink(id=uuid.uuid4(), incident_id=incident.id, alert_id=alert.id, linked_at=utcnow())
            )

        cluster.status = CorrelationClusterStatus.ESCALATED.value
        cluster.escalated_incident_id = incident.id
        await self.session.flush()

        await self.cache.publish(
            f"ws:org:{cluster.organization_id}",
            {"type": "incident_auto_escalated", "incident_id": str(incident.id), "cluster_id": str(cluster.id)},
        )
    async def list_active_clusters(self, organization_id: uuid.UUID) -> list[CorrelationCluster]:
        return await self.clusters.list_active_for_org(organization_id)

    async def get_cluster(self, cluster_id: uuid.UUID, organization_id: uuid.UUID) -> CorrelationCluster:
        cluster = await self.clusters.get_with_members(cluster_id)
        if cluster is None or cluster.organization_id != organization_id:
            raise NotFoundError("Correlation cluster not found")
        return cluster

    async def dismiss_cluster(self, cluster_id: uuid.UUID, organization_id: uuid.UUID) -> CorrelationCluster:
        cluster = await self.get_cluster(cluster_id, organization_id)
        cluster.status = CorrelationClusterStatus.DISMISSED.value
        await self.session.flush()
        return cluster