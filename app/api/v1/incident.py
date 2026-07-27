"""Incident Management endpoints."""
from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_db, require_permissions
from app.core.cache import CacheManager
from app.models.identity import User
from app.schemas.identity import PaginatedResponse
from app.schemas.incidents import (
    IncidentAddNote,
    IncidentCreate,
    IncidentRead,
    IncidentStatsResponse,
    IncidentUpdateRequest,
)
from app.services.incident_service import IncidentService

router = APIRouter(prefix="/incidents", tags=["Incident Management"])


def _to_read(incident) -> dict:  # noqa: ANN001
    return {
        "id": incident.id,
        "organization_id": incident.organization_id,
        "title": incident.title,
        "description": incident.description,
        "status": incident.status,
        "priority": incident.priority,
        "category": incident.category,
        "assigned_to_id": incident.assigned_to_id,
        "assigned_team_id": incident.assigned_team_id,
        "created_by_id": incident.created_by_id,
        "metadata_json": incident.metadata_json,
        "resolved_at": incident.resolved_at,
        "closed_at": incident.closed_at,
        "created_at": incident.created_at,
        "updates": incident.updates,
        "linked_alert_ids": [link.alert_id for link in incident.linked_alerts],
    }


@router.get("", response_model=PaginatedResponse)
async def list_incidents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    assigned_to_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(require_permissions("incidents:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = IncidentService(db, cache)
    items, total = await service.list_filtered(
        user.organization_id,
        page=page,
        page_size=page_size,
        status=status_filter,
        priority=priority,
        assigned_to_id=assigned_to_id,
    )
    return {
        "items": [IncidentRead.model_validate(_to_read(i)) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


@router.get("/stats", response_model=IncidentStatsResponse)
async def get_incident_stats(
    user: User = Depends(require_permissions("incidents:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = IncidentService(db, cache)
    return await service.get_stats(user.organization_id)


@router.get("/{incident_id}", response_model=IncidentRead)
async def get_incident(
    incident_id: uuid.UUID,
    user: User = Depends(require_permissions("incidents:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = IncidentService(db, cache)
    incident = await service.get(incident_id, user.organization_id)
    return _to_read(incident)


@router.post("", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    actor: User = Depends(require_permissions("incidents:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = IncidentService(db, cache)
    incident = await service.create(actor.organization_id, payload, actor)
    return _to_read(incident)


@router.patch("/{incident_id}", response_model=IncidentRead)
async def update_incident(
    incident_id: uuid.UUID,
    payload: IncidentUpdateRequest,
    user: User = Depends(require_permissions("incidents:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = IncidentService(db, cache)
    incident = await service.update(incident_id, user.organization_id, payload)
    return _to_read(incident)


@router.post("/{incident_id}/notes", response_model=IncidentRead)
async def add_incident_note(
    incident_id: uuid.UUID,
    payload: IncidentAddNote,
    actor: User = Depends(require_permissions("incidents:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = IncidentService(db, cache)
    incident = await service.add_note(incident_id, actor.organization_id, payload, actor)
    return _to_read(incident)


@router.post("/{incident_id}/assign", response_model=IncidentRead)
async def assign_incident(
    incident_id: uuid.UUID,
    payload: IncidentUpdateRequest,
    actor: User = Depends(require_permissions("incidents:assign")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = IncidentService(db, cache)
    incident = await service.update(incident_id, actor.organization_id, payload)
    return _to_read(incident)