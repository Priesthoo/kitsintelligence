"""Notification inbox endpoints: list, unread stats, mark-read, preferences."""
from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.identity import User
from app.schemas.identity import PaginatedResponse
from app.schemas.notifications import (
    BulkMarkReadRequest,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
    NotificationStatsResponse,
)
from app.services.notifications_read_service import NotificationReadService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=PaginatedResponse)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = NotificationReadService(db)
    items, total = await service.list_for_user(user.id, page=page, page_size=page_size, unread_only=unread_only)
    return {
        "items": [NotificationRead.model_validate(n) for n in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


@router.get("/stats", response_model=NotificationStatsResponse)
async def get_notification_stats(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    service = NotificationReadService(db)
    return await service.get_stats(user.id)


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> object:
    service = NotificationReadService(db)
    return await service.mark_read(user.id, notification_id)


@router.post("/mark-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read_bulk(
    payload: BulkMarkReadRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    service = NotificationReadService(db)
    await service.mark_read_bulk(user.id, payload.notification_ids, payload.mark_all)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    service = NotificationReadService(db)
    await service.delete(user.id, notification_id)


@router.get("/preferences", response_model=list[NotificationPreferenceRead])
async def list_notification_preferences(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list:
    service = NotificationReadService(db)
    return await service.list_preferences(user.id)


@router.put("/preferences", response_model=NotificationPreferenceRead)
async def update_notification_preference(
    payload: NotificationPreferenceUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> object:
    service = NotificationReadService(db)
    return await service.update_preference(user.id, payload.category, payload.channel, payload.is_enabled)