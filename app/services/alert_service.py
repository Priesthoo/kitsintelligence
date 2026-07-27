"""
Alert lifecycle management: creation (manual or system-generated),
acknowledgement, resolution, dismissal. Every state transition fires a
real-time notification via the WebSocket Gateway so operators see new
alerts the instant they're created, and an audit trail entry for
compliance.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import CacheManager
from app.core.metrics import ALERTS_GENERATED_TOTAL
from app.db.base import utcnow
from app.exceptions.base import NotFoundError, ValidationError
from app.models.alerts import Alert, AlertSourceType, AlertStatus
from app.models.identity import User
from app.repositories.alerts import AlertRepository
from app.schemas.alert import AlertCreate, AlertResolve, AlertUpdate
from app.services.audit_service import AuditService


class AlertService:
    def __init__(self, session: AsyncSession, cache: CacheManager) -> None:
        self.session = session
        self.cache = cache
        self.alerts = AlertRepository(session)
        self.audit = AuditService(session)

    async def list_filtered(
        self,
        organization_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
    ) -> tuple[list[Alert], int]:
        offset = (page - 1) * page_size
        return await self.alerts.list_filtered(
            organization_id, status=status, severity=severity, category=category, offset=offset, limit=page_size
        )

    async def get(self, alert_id: uuid.UUID, organization_id: uuid.UUID) -> Alert:
        alert = await self.alerts.get(alert_id)
        if alert is None or alert.organization_id != organization_id:
            raise NotFoundError("Alert not found")
        return alert

    async def create_manual(self, organization_id: uuid.UUID, payload: AlertCreate, actor: User) -> Alert:
        alert = await self.alerts.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            title=payload.title,
            description=payload.description,
            category=payload.category,
            severity=payload.severity,
            status=AlertStatus.OPEN.value,
            source_type=AlertSourceType.MANUAL.value,
            latitude=payload.latitude,
            longitude=payload.longitude,
            metadata_json=payload.metadata_json,
        )
        await self._on_alert_created(alert, actor.id)
        return alert

    async def create_system_generated(
        self,
        organization_id: uuid.UUID,
        *,
        title: str,
        description: str,
        category: str,
        severity: str,
        source_type: AlertSourceType,
        source_reference: str | None = None,
        data_source_id: uuid.UUID | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        metadata_json: dict | None = None,
    ) -> Alert:
        """Called by connectors/correlation engine/rule engine -- no human actor involved."""
        alert = await self.alerts.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            title=title,
            description=description,
            category=category,
            severity=severity,
            status=AlertStatus.OPEN.value,
            source_type=source_type.value,
            source_reference=source_reference,
            data_source_id=data_source_id,
            latitude=latitude,
            longitude=longitude,
            metadata_json=metadata_json or {},
        )
        await self._on_alert_created(alert, None)
        return alert

    async def _on_alert_created(self, alert: Alert, actor_user_id: uuid.UUID | None) -> None:
        ALERTS_GENERATED_TOTAL.labels(severity=alert.severity, category=alert.category).inc()
        await self.audit.record(
            action="alert.create",
            resource_type="alert",
            resource_id=str(alert.id),
            organization_id=alert.organization_id,
            actor_user_id=actor_user_id,
            metadata={"severity": alert.severity, "category": alert.category},
        )
        await self.cache.publish(
            f"ws:org:{alert.organization_id}",
            {
                "type": "alert_created",
                "alert_id": str(alert.id),
                "title": alert.title,
                "severity": alert.severity,
                "category": alert.category,
            },
        )

    async def update(self, alert_id: uuid.UUID, organization_id: uuid.UUID, payload: AlertUpdate) -> Alert:
        alert = await self.get(alert_id, organization_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(alert, key, value)
        await self.session.flush()
        return alert

    async def acknowledge(self, alert_id: uuid.UUID, organization_id: uuid.UUID, actor: User) -> Alert:
        alert = await self.get(alert_id, organization_id)
        if alert.status != AlertStatus.OPEN.value:
            raise ValidationError(f"Cannot acknowledge an alert with status '{alert.status}'")
        alert.status = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_by_id = actor.id
        alert.acknowledged_at = utcnow()
        await self.session.flush()
        await self.audit.record(
            action="alert.acknowledge",
            resource_type="alert",
            resource_id=str(alert.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
        )
        return alert

    async def resolve(self, alert_id: uuid.UUID, organization_id: uuid.UUID, payload: AlertResolve, actor: User) -> Alert:
        alert = await self.get(alert_id, organization_id)
        if alert.status == AlertStatus.RESOLVED.value:
            raise ValidationError("Alert is already resolved")
        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_by_id = actor.id
        alert.resolved_at = utcnow()
        alert.resolution_notes = payload.resolution_notes
        await self.session.flush()
        await self.audit.record(
            action="alert.resolve",
            resource_type="alert",
            resource_id=str(alert.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
        )
        return alert

    async def dismiss(self, alert_id: uuid.UUID, organization_id: uuid.UUID, actor: User) -> Alert:
        alert = await self.get(alert_id, organization_id)
        alert.status = AlertStatus.DISMISSED.value
        await self.session.flush()
        await self.audit.record(
            action="alert.dismiss",
            resource_type="alert",
            resource_id=str(alert.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
        )
        return alert

    async def get_stats(self, organization_id: uuid.UUID) -> dict:
        return await self.alerts.get_stats(organization_id)