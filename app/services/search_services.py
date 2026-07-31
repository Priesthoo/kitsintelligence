"""
Cross-entity Search service. Searches Alerts, Incidents, Data Sources, and
Users by simple case-insensitive substring match on their primary
text fields. This is a straightforward ILIKE-based implementation --
sufficient for moderate data volumes; if/when search volume or corpus
size grows, this is the natural place to swap in Postgres full-text
search (tsvector) or an external search engine without changing the
API contract.
"""
from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerts import Alert
from app.models.data_sources import DataSource
from app.models.identity import User

MAX_RESULTS_PER_TYPE = 20


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, organization_id: uuid.UUID, query: str) -> dict:
        pattern = f"%{query}%"
        results: dict[str, list[dict]] = {"alerts": [], "incidents": [], "data_sources": [], "users": []}

        alerts_result = await self.session.execute(
            select(Alert)
            .where(
                Alert.organization_id == organization_id,
                or_(Alert.title.ilike(pattern), Alert.description.ilike(pattern), Alert.category.ilike(pattern)),
            )
            .limit(MAX_RESULTS_PER_TYPE)
        )
        results["alerts"] = [
            {"id": str(a.id), "title": a.title, "severity": a.severity, "status": a.status, "created_at": a.created_at.isoformat()}
            for a in alerts_result.scalars().all()
        ]

        try:
            from app.models.incident import Incident

            incidents_result = await self.session.execute(
                select(Incident)
                .where(
                    Incident.organization_id == organization_id,
                    or_(Incident.title.ilike(pattern), Incident.description.ilike(pattern)),
                )
                .limit(MAX_RESULTS_PER_TYPE)
            )
            results["incidents"] = [
                {"id": str(i.id), "title": i.title, "priority": i.priority, "status": i.status, "created_at": i.created_at.isoformat()}
                for i in incidents_result.scalars().all()
            ]
        except Exception:  # noqa: BLE001
            pass

        sources_result = await self.session.execute(
            select(DataSource)
            .where(
                (DataSource.is_global.is_(True)) | (DataSource.organization_id == organization_id),
                DataSource.is_deleted.is_(False),
                or_(DataSource.name.ilike(pattern), DataSource.slug.ilike(pattern), DataSource.category.ilike(pattern)),
            )
            .limit(MAX_RESULTS_PER_TYPE)
        )
        results["data_sources"] = [
            {"id": str(s.id), "name": s.name, "slug": s.slug, "category": s.category, "status": s.status}
            for s in sources_result.scalars().all()
        ]

        users_result = await self.session.execute(
            select(User)
            .where(
                User.organization_id == organization_id,
                User.is_deleted.is_(False),
                or_(User.full_name.ilike(pattern), User.email.ilike(pattern)),
            )
            .limit(MAX_RESULTS_PER_TYPE)
        )
        results["users"] = [
            {"id": str(u.id), "full_name": u.full_name, "email": u.email, "status": u.status}
            for u in users_result.scalars().all()
        ]

        total = sum(len(v) for v in results.values())
        return {"query": query, "total_results": total, "results": results}