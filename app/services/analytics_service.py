"""
Analytics & Timeline & Activity Feed service. All three read from data
already produced by other modules (Alerts, Incidents, Audit Log) -- there's
no separate analytics data store; this is a query/aggregation layer over
existing tables, kept as one service since the three views share so much
of the same underlying date-bucketing logic.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.alerts import Alert
from app.models.identity import AuditLog

DEFAULT_TREND_DAYS = 30


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_overview(self, organization_id: uuid.UUID) -> dict:
        now = utcnow()
        cutoff = now - timedelta(days=DEFAULT_TREND_DAYS)

        severity_result = await self.session.execute(
            select(Alert.severity, func.count())
            .where(Alert.organization_id == organization_id, Alert.created_at >= cutoff)
            .group_by(Alert.severity)
        )
        alerts_by_severity = dict(severity_result.all())

        alerts_trend = await self._daily_trend(Alert, organization_id, cutoff)

        category_result = await self.session.execute(
            select(Alert.category, func.count())
            .where(Alert.organization_id == organization_id, Alert.created_at >= cutoff)
            .group_by(Alert.category)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_categories = [{"category": c, "count": n} for c, n in category_result.all()]

        incidents_by_priority: dict[str, int] = {}
        incidents_trend: list = []
        mttr: float | None = None
        try:
            from app.models.incident import Incident

            priority_result = await self.session.execute(
                select(Incident.priority, func.count())
                .where(Incident.organization_id == organization_id, Incident.created_at >= cutoff)
                .group_by(Incident.priority)
            )
            incidents_by_priority = dict(priority_result.all())
            incidents_trend = await self._daily_trend(Incident, organization_id, cutoff)

            resolved_result = await self.session.execute(
                select(Incident.created_at, Incident.resolved_at).where(
                    Incident.organization_id == organization_id, Incident.resolved_at.is_not(None)
                )
            )
            rows = resolved_result.all()
            if rows:
                total_seconds = sum((r.resolved_at - r.created_at).total_seconds() for r in rows)
                mttr = round((total_seconds / len(rows)) / 3600, 2)
        except Exception:  # noqa: BLE001
            pass

        return {
            "generated_at": now,
            "alerts_by_severity": alerts_by_severity,
            "alerts_trend": alerts_trend,
            "incidents_by_priority": incidents_by_priority,
            "incidents_trend": incidents_trend,
            "mean_time_to_resolve_hours": mttr,
            "top_alert_categories": top_categories,
        }

    async def _daily_trend(self, model, organization_id: uuid.UUID, cutoff) -> list[dict]:  # noqa: ANN001
        result = await self.session.execute(
            select(func.date_trunc("day", model.created_at), func.count())
            .where(model.organization_id == organization_id, model.created_at >= cutoff)
            .group_by(func.date_trunc("day", model.created_at))
            .order_by(func.date_trunc("day", model.created_at))
        )
        return [{"period": period.date().isoformat(), "count": count} for period, count in result.all()]

    async def get_series(self, organization_id: uuid.UUID, metric: str, *, days: int = 30) -> dict:
        cutoff = utcnow() - timedelta(days=days)
        model_map = {"alerts": Alert}
        try:
            from app.models.incident import Incident

            model_map["incidents"] = Incident
        except Exception:  # noqa: BLE001
            pass

        if metric not in model_map:
            return {"metric": metric, "interval": "day", "points": []}

        points = await self._daily_trend(model_map[metric], organization_id, cutoff)
        return {"metric": metric, "interval": "day", "points": points}

    async def get_timeline(
        self, organization_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[dict], int]:
        entries: list[dict] = []

        alerts_result = await self.session.execute(
            select(Alert)
            .where(Alert.organization_id == organization_id)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
        for alert in alerts_result.scalars().all():
            entries.append(
                {
                    "id": str(alert.id),
                    "entry_type": "alert",
                    "title": alert.title,
                    "description": alert.description,
                    "severity_or_priority": alert.severity,
                    "occurred_at": alert.created_at,
                    "resource_type": "alert",
                    "resource_id": str(alert.id),
                }
            )

        try:
            from app.models.incident import Incident

            incidents_result = await self.session.execute(
                select(Incident)
                .where(Incident.organization_id == organization_id)
                .order_by(Incident.created_at.desc())
                .limit(limit)
            )
            for incident in incidents_result.scalars().all():
                entries.append(
                    {
                        "id": str(incident.id),
                        "entry_type": "incident",
                        "title": incident.title,
                        "description": incident.description,
                        "severity_or_priority": incident.priority,
                        "occurred_at": incident.created_at,
                        "resource_type": "incident",
                        "resource_id": str(incident.id),
                    }
                )
        except Exception:  # noqa: BLE001
            pass

        entries.sort(key=lambda e: e["occurred_at"], reverse=True)
        total = len(entries)
        return entries[offset : offset + limit], total

    async def get_activity_feed(
        self, organization_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[AuditLog], int]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_stmt = select(func.count()).select_from(AuditLog).where(AuditLog.organization_id == organization_id)

        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)
        return list(result.scalars().all()), count_result.scalar_one()