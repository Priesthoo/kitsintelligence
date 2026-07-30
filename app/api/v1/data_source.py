
"""Data Sources / Connector Framework admin endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permissions
from app.models.identity import User
from app.schemas.data_sources import (
    ConnectorCatalogEntry,
    DataSourceCreate,
    DataSourceRead,
    DataSourceUpdate,
    HydrationRunRead,
)
from app.services.data_source_service import DataSourceService

router = APIRouter(prefix="/data-sources", tags=["Data Sources"])


@router.get("/connectors/catalog", response_model=list[ConnectorCatalogEntry])
async def list_connector_catalog(
    _: User = Depends(require_permissions("connectors:read")), db: AsyncSession = Depends(get_db)
) -> list:
    service = DataSourceService(db)
    keys = await service.list_connector_keys()
    return [ConnectorCatalogEntry(key=k) for k in keys]


@router.get("", response_model=list[DataSourceRead])
async def list_data_sources(
    user: User = Depends(require_permissions("data_sources:read")), db: AsyncSession = Depends(get_db)
) -> list:
    service = DataSourceService(db)
    return await service.list_for_org(user.organization_id)


@router.get("/{data_source_id}", response_model=DataSourceRead)
async def get_data_source(
    data_source_id: uuid.UUID,
    _: User = Depends(require_permissions("data_sources:read")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = DataSourceService(db)
    return await service.get(data_source_id)


@router.post("", response_model=DataSourceRead, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    payload: DataSourceCreate,
    actor: User = Depends(require_permissions("data_sources:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = DataSourceService(db)
    return await service.create(payload, actor)


@router.patch("/{data_source_id}", response_model=DataSourceRead)
async def update_data_source(
    data_source_id: uuid.UUID,
    payload: DataSourceUpdate,
    actor: User = Depends(require_permissions("data_sources:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = DataSourceService(db)
    return await service.update(data_source_id, payload, actor)


@router.delete("/{data_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    data_source_id: uuid.UUID,
    actor: User = Depends(require_permissions("data_sources:delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = DataSourceService(db)
    await service.delete(data_source_id, actor)


@router.post("/{data_source_id}/credentials/{credential_key}", status_code=status.HTTP_204_NO_CONTENT)
async def rotate_credential(
    data_source_id: uuid.UUID,
    credential_key: str,
    value: str = Query(..., min_length=1),
    actor: User = Depends(require_permissions("data_sources:write")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = DataSourceService(db)
    await service.rotate_credential(data_source_id, credential_key, value, actor)


@router.post("/{data_source_id}/sync-now", status_code=status.HTTP_202_ACCEPTED)
async def sync_now(
    data_source_id: uuid.UUID,
    _: User = Depends(require_permissions("connectors:execute")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = DataSourceService(db)
    await service.trigger_sync_now(data_source_id)
    return {"message": "Sync triggered"}


@router.get("/{data_source_id}/runs", response_model=list[HydrationRunRead])
async def list_recent_runs(
    data_source_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permissions("data_sources:read")),
    db: AsyncSession = Depends(get_db),
) -> list:
    service = DataSourceService(db)
    return await service.list_recent_runs(data_source_id, limit=limit)