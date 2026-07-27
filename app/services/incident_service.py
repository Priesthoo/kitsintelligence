"""
Incident lifecycle management: creation (optionally escalating one or more
existing Alerts), assignment, status transitions with a running note
timeline, and closure. Escalating an Alert flips its
`is_escalated_to_incident` flag so Alert views can show the link back.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import CacheManager
from app.db.base import utcnow
from app.exceptions.base import NotFoundError, ValidationError
from app.models.identity import User
from app.models.incident import Incident, IncidentStatus
from app.repositories.alerts import AlertRepository
from app.repositories.incident import (
    IncidentAlertLinkRepository,
    IncidentRepository,
    IncidentUpdateRepository,
)
from app.schemas.incidents import IncidentAddNote, IncidentCreate, IncidentUpdateRequest
from app.services.audit_service import AuditService


class IncidentService:
    def __init__(self, session: AsyncSession, cache: CacheManager) -> None:
        self.session = session
        self.cache = cache
        self.incidents = IncidentRepository(session)
        self.updates = IncidentUpdateRepository(session)
        self.links = IncidentAlertLinkRepository(session)
        self.alerts = AlertRepository(session)
        self.audit = AuditService(session)

    async def list_filtered(
        self,
        organization_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        priority: str | None = None,
        assigned_to_id: uuid.UUID | None = None,
    ) -> tuple[list[Incident], int]:
        offset = (page - 1) * page_size
        return await self.incidents.list_filtered(
            organization_id,
            status=status,
            priority=priority,
            assigned_to_id=assigned_to_id,
            offset=offset,
            limit=page_size,
        )

    async def get(self, incident_id: uuid.UUID, organization_id: uuid.UUID) -> Incident:
        incident = await self.incidents.get_with_details(incident_id)
        if incident is None or incident.organization_id != organization_id:
            raise NotFoundError("Incident not found")
        return incident

    async def create(self, organization_id: uuid.UUID, payload: IncidentCreate, actor: User) -> Incident:
        incident = await self.incidents.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            title=payload.title,
            description=payload.description,
            category=payload.category,
            priority=payload.priority,
            status=IncidentStatus.OPEN.value,
            assigned_to_id=payload.assigned_to_id,
            assigned_team_id=payload.assigned_team_id,
            created_by_id=actor.id,
            metadata_json=payload.metadata_json,
        )

        for alert_id in payload.alert_ids:
            alert = await self.alerts.get(alert_id)
            if alert is None or alert.organization_id != organization_id:
                continue
            await self.links.create(
                id=uuid.uuid4(), incident_id=incident.id, alert_id=alert_id, linked_at=utcnow()
            )
            alert.is_escalated_to_incident = True

        await self.session.flush()
        await self.audit.record(
            action="incident.create",
            resource_type="incident",
            resource_id=str(incident.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
        )
        await self.cache.publish(
            f"ws:org:{organization_id}",
            {
                "type": "incident_created",
                "incident_id": str(incident.id),
                "title": incident.title,
                "priority": incident.priority,
            },
        )
        return await self.get(incident.id, organization_id)

    async def update(self, incident_id: uuid.UUID, organization_id: uuid.UUID, payload: IncidentUpdateRequest) -> Incident:
        incident = await self.get(incident_id, organization_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(incident, key, value)
        await self.session.flush()
        return await self.get(incident_id, organization_id)

    async def add_note(
        self, incident_id: uuid.UUID, organization_id: uuid.UUID, payload: IncidentAddNote, actor: User
    ) -> Incident:
        incident = await self.get(incident_id, organization_id)

        if payload.status_change_to is not None:
            valid_statuses = {s.value for s in IncidentStatus}
            if payload.status_change_to not in valid_statuses:
                raise ValidationError(f"Invalid status '{payload.status_change_to}'")
            incident.status = payload.status_change_to
            if payload.status_change_to == IncidentStatus.RESOLVED.value:
                incident.resolved_at = utcnow()
            elif payload.status_change_to == IncidentStatus.CLOSED.value:
                incident.closed_at = utcnow()

        await self.updates.create(
            id=uuid.uuid4(),
            incident_id=incident.id,
            author_id=actor.id,
            note=payload.note,
            status_change_to=payload.status_change_to,
            created_at=utcnow(),
        )
        await self.session.flush()

        await self.audit.record(
            action="incident.add_note",
            resource_type="incident",
            resource_id=str(incident.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
            metadata={"status_change_to": payload.status_change_to},
        )
        return await self.get(incident_id, organization_id)

    async def get_stats(self, organization_id: uuid.UUID) -> dict:
        return await self.incidents.get_stats(organization_id)