"""Repository for Incident queries: filtered listing, stats, and detail loading with updates/links."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.base import utcnow
from app.models.incident import Incident, IncidentAlertLink, IncidentStatus, IncidentUpdate
from app.repositories.base import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    model = Incident

    async def get_with_details(self, incident_id: uuid.UUID) -> Incident | None:
        stmt = (
            select(Incident)
            .where(Incident.id == incident_id)
            .options(selectinload(Incident.updates), selectinload(Incident.linked_alerts))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        organization_id: uuid.UUID,
        *,
        status: str | None = None,
        priority: str | None = None,
        assigned_to_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Incident], int]:
        stmt = (
            select(Incident)
            .where(Incident.organization_id == organization_id)
            .options(selectinload(Incident.updates), selectinload(Incident.linked_alerts))
        )
        count_stmt = select(func.count()).select_from(Incident).where(Incident.organization_id == organization_id)

        if status:
            stmt = stmt.where(Incident.status == status)
            count_stmt = count_stmt.where(Incident.status == status)
        if priority:
            stmt = stmt.where(Incident.priority == priority)
            count_stmt = count_stmt.where(Incident.priority == priority)
        if assigned_to_id:
            stmt = stmt.where(Incident.assigned_to_id == assigned_to_id)
            count_stmt = count_stmt.where(Incident.assigned_to_id == assigned_to_id)

        stmt = stmt.order_by(Incident.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)
        return list(result.scalars().unique().all()), count_result.scalar_one()

    async def get_stats(self, organization_id: uuid.UUID) -> dict:
        open_result = await self.session.execute(
            select(func.count()).select_from(Incident).where(
                Incident.organization_id == organization_id, Incident.status == IncidentStatus.OPEN.value
            )
        )
        investigating_result = await self.session.execute(
            select(func.count()).select_from(Incident).where(
                Incident.organization_id == organization_id, Incident.status == IncidentStatus.INVESTIGATING.value
            )
        )

        resolved_result = await self.session.execute(
            select(Incident.created_at, Incident.resolved_at).where(
                Incident.organization_id == organization_id, Incident.resolved_at.is_not(None)
            )
        )
        resolved_rows = resolved_result.all()
        mttr_hours: float | None = None
        if resolved_rows:
            total_seconds = sum((r.resolved_at - r.created_at).total_seconds() for r in resolved_rows)
            mttr_hours = round((total_seconds / len(resolved_rows)) / 3600, 2)

        priority_result = await self.session.execute(
            select(Incident.priority, func.count())
            .where(
                Incident.organization_id == organization_id,
                Incident.status.notin_([IncidentStatus.CLOSED.value]),
            )
            .group_by(Incident.priority)
        )

        return {
            "total_open": open_result.scalar_one(),
            "total_investigating": investigating_result.scalar_one(),
            "mean_time_to_resolve_hours": mttr_hours,
            "by_priority": dict(priority_result.all()),
        }


class IncidentUpdateRepository(BaseRepository[IncidentUpdate]):
    model = IncidentUpdate


class IncidentAlertLinkRepository(BaseRepository[IncidentAlertLink]):
    model = IncidentAlertLink