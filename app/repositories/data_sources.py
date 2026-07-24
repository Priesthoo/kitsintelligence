"""Repository extensions for DataSource admin operations (beyond the hydration-engine query in hydration_service.py)."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.data_sources import DataSource, DataSourceCredential, HydrationRun
from app.repositories.base import BaseRepository


class DataSourceAdminRepository(BaseRepository[DataSource]):
    model = DataSource

    async def get_by_slug(self, slug: str) -> DataSource | None:
        stmt = select(DataSource).where(DataSource.slug == slug, DataSource.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_visible_to_org(self, organization_id: uuid.UUID) -> list[DataSource]:
        stmt = select(DataSource).where(
            DataSource.is_deleted.is_(False),
            (DataSource.is_global.is_(True)) | (DataSource.organization_id == organization_id),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class HydrationRunRepository(BaseRepository[HydrationRun]):
    model = HydrationRun

    async def list_recent_for_source(self, data_source_id: uuid.UUID, *, limit: int = 20) -> list[HydrationRun]:
        stmt = (
            select(HydrationRun)
            .where(HydrationRun.data_source_id == data_source_id)
            .order_by(HydrationRun.started_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class DataSourceCredentialRepository(BaseRepository[DataSourceCredential]):
    model = DataSourceCredential

    async def list_for_source(self, data_source_id: uuid.UUID) -> list[DataSourceCredential]:
        stmt = select(DataSourceCredential).where(DataSourceCredential.data_source_id == data_source_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(self, data_source_id: uuid.UUID, credential_key: str, encrypted_value: str) -> DataSourceCredential:
        existing = await self.get_or_none(data_source_id=data_source_id, credential_key=credential_key)
        if existing:
            existing.encrypted_value = encrypted_value
            from app.db.base import utcnow

            existing.rotated_at = utcnow()
            await self.session.flush()
            return existing
        return await self.create(
            id=uuid.uuid4(),
            data_source_id=data_source_id,
            credential_key=credential_key,
            encrypted_value=encrypted_value,
        )