"""
Dashboard & System Status aggregation. Pulls a cross-section of everything
else the platform tracks -- user activity, alert volume, incident counts,
per-category hydration health, and component-level liveness -- into two
purpose-built read models for the operator's landing screen.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import CacheManager
from app.db.base import utcnow
from app.db.session import check_database_connection
from app.models.data_sources import DataSource, DataSourceCategory
from app.models.identity import Organization, User
from app.repositories.data_sources import DataSourceAdminRepository
from app.websockets.manager import connection_manager

STALE_THRESHOLD_MULTIPLIER = 3


class DashboardService:
    def __init__(self, session: AsyncSession, cache: CacheManager) -> None:
        self.session = session
        self.cache = cache
        self.sources = DataSourceAdminRepository(session)

    async def get_dashboard(self, user: User) -> dict:
        now = utcnow()

        org_result = await self.session.execute(select(Organization).where(Organization.id == user.organization_id))
        org = org_result.scalar_one()

        active_users_result = await self.session.execute(
            select(func.count()).select_from(User).where(
                User.organization_id == user.organization_id,
                User.is_deleted.is_(False),
                User.status == "active",
            )
        )
        active_users = active_users_result.scalar_one()

        category_health = await self._category_health(user.organization_id)

        # Alerts/incidents modules are wired in below once their models exist;
        # until then this reports zero rather than raising, so the dashboard
        # degrades gracefully as modules come online incrementally.
        alerts_24h = await self._safe_count_alerts_last_24h(user.organization_id)
        open_incidents = await self._safe_count_open_incidents(user.organization_id)
        recent_activity = await self._recent_activity_count(user.organization_id)

        return {
            "generated_at": now,
            "organization_name": org.name,
            "active_users": active_users,
            "total_alerts_last_24h": alerts_24h,
            "open_incidents": open_incidents,
            "category_health": category_health,
            "recent_activity_count": recent_activity,
        }

    async def _category_health(self, organization_id) -> list[dict]:  # noqa: ANN001
        sources = await self.sources.list_visible_to_org(organization_id)
        by_category: dict[str, list[DataSource]] = {}
        for s in sources:
            by_category.setdefault(s.category, []).append(s)

        now = utcnow()
        results = []
        for category, cat_sources in by_category.items():
            healthy, stale, error, total_records = 0, 0, 0, 0
            for s in cat_sources:
                if s.status == "error":
                    error += 1
                    continue
                is_stale = True
                if s.last_success_at:
                    elapsed = (now - s.last_success_at).total_seconds()
                    is_stale = elapsed > (s.sync_interval_seconds * STALE_THRESHOLD_MULTIPLIER)
                if is_stale:
                    stale += 1
                else:
                    healthy += 1

                cache_key = f"hydrated:{category}:{s.slug}"
                payload = await self.cache.get_json(cache_key)
                total_records += payload.get("record_count", 0) if payload else 0

            results.append(
                {
                    "category": category,
                    "total_sources": len(cat_sources),
                    "healthy_sources": healthy,
                    "stale_sources": stale,
                    "error_sources": error,
                    "total_records": total_records,
                }
            )
        return results

    async def _safe_count_alerts_last_24h(self, organization_id) -> int:  # noqa: ANN001
        try:
            from datetime import timedelta

            from app.models.alerts import Alert

            cutoff = utcnow() - timedelta(hours=24)
            result = await self.session.execute(
                select(func.count()).select_from(Alert).where(
                    Alert.organization_id == organization_id, Alert.created_at >= cutoff
                )
            )
            return result.scalar_one()
        except Exception:  # noqa: BLE001
            return 0

    async def _safe_count_open_incidents(self, organization_id) -> int:  # noqa: ANN001
        try:
            from app.models.incident import Incident, IncidentStatus

            result = await self.session.execute(
                select(func.count()).select_from(Incident).where(
                    Incident.organization_id == organization_id,
                    Incident.status.in_([IncidentStatus.OPEN.value, IncidentStatus.INVESTIGATING.value]),
                )
            )
            return result.scalar_one()
        except Exception:  # noqa: BLE001
            return 0

    async def _recent_activity_count(self, organization_id) -> int:  # noqa: ANN001
        from datetime import timedelta

        from app.models.identity import AuditLog

        cutoff = utcnow() - timedelta(hours=24)
        result = await self.session.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.organization_id == organization_id, AuditLog.created_at >= cutoff
            )
        )
        return result.scalar_one()

    async def get_system_status(self) -> dict:
        now = utcnow()
        components = []

        db_ok = await check_database_connection()
        components.append({"name": "database", "status": "ok" if db_ok else "down", "detail": None})

        redis_ok = await self.cache.ping()
        components.append({"name": "redis", "status": "ok" if redis_ok else "down", "detail": None})

        all_sources_result = await self.session.execute(select(DataSource).where(DataSource.is_deleted.is_(False)))
        all_sources = list(all_sources_result.scalars().all())
        active_sources = [s for s in all_sources if s.status == "active"]
        circuit_open = [s for s in all_sources if s.is_circuit_open]

        components.append(
            {
                "name": "connector_framework",
                "status": "degraded" if circuit_open else "ok",
                "detail": f"{len(circuit_open)} circuit breaker(s) open" if circuit_open else None,
            }
        )

        hydration_jobs_last_hour = await self._hydration_jobs_last_hour()
        components.append({"name": "hydration_engine", "status": "ok", "detail": None})

        overall = "ok"
        if not db_ok or not redis_ok:
            overall = "critical"
        elif circuit_open:
            overall = "degraded"

        return {
            "generated_at": now,
            "overall_status": overall,
            "components": components,
            "active_data_sources": len(active_sources),
            "circuit_breakers_open": len(circuit_open),
            "hydration_jobs_last_hour": hydration_jobs_last_hour,
            "websocket_connections": connection_manager.active_connection_count,
        }

    async def _hydration_jobs_last_hour(self) -> int:
        from datetime import timedelta

        from app.models.data_sources import HydrationRun

        cutoff = utcnow() - timedelta(hours=1)
        result = await self.session.execute(
            select(func.count()).select_from(HydrationRun).where(HydrationRun.started_at >= cutoff)
        )
        return result.scalar_one()