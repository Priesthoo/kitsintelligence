"""
Data Sources admin service: CRUD over connector configuration, credential
rotation (encrypted at rest via app.utils.crypto), manual "sync now"
triggering, and hydration-run history for observability.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import ConnectorRegistry
from app.exceptions.base import AlreadyExistsError, NotFoundError, ValidationError
from app.models.data_sources import DataSource, DataSourceStatus, HydrationRun
from app.models.identity import User
from app.repositories.data_sources import (
    DataSourceAdminRepository,
    DataSourceCredentialRepository,
    HydrationRunRepository,
)
from app.schemas.data_sources import DataSourceCreate, DataSourceUpdate
from app.services.audit_service import AuditService
from app.utils.crypto import encrypt_value


class DataSourceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sources = DataSourceAdminRepository(session)
        self.credentials = DataSourceCredentialRepository(session)
        self.runs = HydrationRunRepository(session)
        self.audit = AuditService(session)

    async def list_connector_keys(self) -> list[str]:
        return ConnectorRegistry.all_keys()

    async def list_for_org(self, organization_id: uuid.UUID) -> list[DataSource]:
        return await self.sources.list_visible_to_org(organization_id)

    async def get(self, data_source_id: uuid.UUID) -> DataSource:
        source = await self.sources.get(data_source_id)
        if source is None:
            raise NotFoundError("Data source not found")
        return source

    async def create(self, payload: DataSourceCreate, actor: User) -> DataSource:
        if payload.connector_key not in ConnectorRegistry.all_keys():
            raise ValidationError(
                f"Unknown connector_key '{payload.connector_key}'. "
                f"Available: {', '.join(ConnectorRegistry.all_keys())}"
            )
        if await self.sources.get_by_slug(payload.slug):
            raise AlreadyExistsError(f"A data source with slug '{payload.slug}' already exists")

        source = await self.sources.create(
            id=uuid.uuid4(),
            organization_id=payload.organization_id,
            name=payload.name,
            slug=payload.slug,
            category=payload.category,
            connector_key=payload.connector_key,
            connector_type=payload.connector_type,
            base_url=payload.base_url,
            config_json=payload.config_json,
            sync_interval_seconds=payload.sync_interval_seconds,
            priority=payload.priority,
            is_global=payload.is_global,
            status=DataSourceStatus.ACTIVE.value,
        )

        for cred in payload.credentials:
            await self.credentials.upsert(source.id, cred.credential_key, encrypt_value(cred.value))

        await self.audit.record(
            action="data_source.create",
            resource_type="data_source",
            resource_id=str(source.id),
            organization_id=payload.organization_id,
            actor_user_id=actor.id,
        )
        return source

    async def update(self, data_source_id: uuid.UUID, payload: DataSourceUpdate, actor: User) -> DataSource:
        source = await self.get(data_source_id)
        data = payload.model_dump(exclude_unset=True)

        if "status" in data and data["status"] not in {s.value for s in DataSourceStatus}:
            raise ValidationError(f"Invalid status '{data['status']}'")

        for key, value in data.items():
            setattr(source, key, value)

        if payload.status == DataSourceStatus.ACTIVE.value:
            source.consecutive_failures = 0
            source.circuit_open_until = None

        await self.session.flush()
        await self.audit.record(
            action="data_source.update",
            resource_type="data_source",
            resource_id=str(source.id),
            organization_id=source.organization_id,
            actor_user_id=actor.id,
            metadata=data,
        )
        return source

    async def rotate_credential(self, data_source_id: uuid.UUID, credential_key: str, value: str, actor: User) -> None:
        source = await self.get(data_source_id)
        await self.credentials.upsert(source.id, credential_key, encrypt_value(value))
        await self.audit.record(
            action="data_source.credential_rotated",
            resource_type="data_source",
            resource_id=str(source.id),
            organization_id=source.organization_id,
            actor_user_id=actor.id,
            metadata={"credential_key": credential_key},
        )

    async def delete(self, data_source_id: uuid.UUID, actor: User) -> None:
        source = await self.get(data_source_id)
        await self.sources.delete(source)
        await self.audit.record(
            action="data_source.delete",
            resource_type="data_source",
            resource_id=str(source.id),
            organization_id=source.organization_id,
            actor_user_id=actor.id,
        )

    async def trigger_sync_now(self, data_source_id: uuid.UUID) -> None:
        source = await self.get(data_source_id)
        from app.workers.tasks.hydration_task import hydrate_source_now

        hydrate_source_now.delay(str(source.id))

    async def list_recent_runs(self, data_source_id: uuid.UUID, *, limit: int = 20) -> list[HydrationRun]:
        await self.get(data_source_id)  # validates existence
        return await self.runs.list_recent_for_source(data_source_id, limit=limit)