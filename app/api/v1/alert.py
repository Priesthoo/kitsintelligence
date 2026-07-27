"""Alert management endpoints."""
from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_db, require_permissions
from app.core.cache import CacheManager
from app.models.identity import User
from app.schemas.alert import (
    AlertCreate,
    AlertRead,
    AlertResolve,
    AlertStatsResponse,
    AlertUpdate,
)
from app.schemas.identity import PaginatedResponse
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=PaginatedResponse)
async def list_alerts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    user: User = Depends(require_permissions("alerts:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = AlertService(db, cache)
    items, total = await service.list_filtered(
        user.organization_id, page=page, page_size=page_size, status=status_filter, severity=severity, category=category
    )
    return {
        "items": [AlertRead.model_validate(a) for a in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats(
    user: User = Depends(require_permissions("alerts:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = AlertService(db, cache)
    return await service.get_stats(user.organization_id)


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: uuid.UUID,
    user: User = Depends(require_permissions("alerts:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> object:
    service = AlertService(db, cache)
    return await service.get(alert_id, user.organization_id)


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: AlertCreate,
    actor: User = Depends(require_permissions("alerts:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> object:
    service = AlertService(db, cache)
    return await service.create_manual(actor.organization_id, payload, actor)


@router.patch("/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: uuid.UUID,
    payload: AlertUpdate,
    user: User = Depends(require_permissions("alerts:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> object:
    service = AlertService(db, cache)
    return await service.update(alert_id, user.organization_id, payload)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    actor: User = Depends(require_permissions("alerts:acknowledge")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> object:
    service = AlertService(db, cache)
    return await service.acknowledge(alert_id, actor.organization_id, actor)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: uuid.UUID,
    payload: AlertResolve,
    actor: User = Depends(require_permissions("alerts:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> object:
    service = AlertService(db, cache)
    return await service.resolve(alert_id, actor.organization_id, payload, actor)


@router.post("/{alert_id}/dismiss", response_model=AlertRead)
async def dismiss_alert(
    alert_id: uuid.UUID,
    actor: User = Depends(require_permissions("alerts:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> object:
    service = AlertService(db, cache)
    return await service.dismiss(alert_id, actor.organization_id, actor)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: uuid.UUID,
    user: User = Depends(require_permissions("alerts:delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    from app.repositories.alerts import AlertRepository
    from app.exceptions.base import NotFoundError

    repo = AlertRepository(db)
    alert = await repo.get(alert_id)
    if alert is None or alert.organization_id != user.organization_id:
        raise NotFoundError("Alert not found")
    await repo.delete(alert, hard=True)