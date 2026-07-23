"""User management endpoints, scoped to the caller's organization."""
from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_permissions
from app.models.identity import User
from app.schemas.identity import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyRead,
    PaginatedResponse,
    UserAdminUpdate,
    UserInvite,
    UserRead,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(require_permissions("users:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = UserService(db)
    items, total = await service.list_for_org(
        user.organization_id, page=page, page_size=page_size, status=status_filter
    )
    return {
        "items": [UserRead.model_validate(u) for u in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    _: User = Depends(require_permissions("users:read")),
    db: AsyncSession = Depends(get_db),
) -> User:
    service = UserService(db)
    return await service.get_by_id(user_id)


@router.post("/invite", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def invite_user(
    payload: UserInvite,
    actor: User = Depends(require_permissions("users:write")),
    db: AsyncSession = Depends(get_db),
) -> User:
    service = UserService(db)
    return await service.invite_user(actor.organization_id, payload, actor)


@router.patch("/me", response_model=UserRead)
async def update_my_profile(
    payload: UserUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> User:
    service = UserService(db)
    return await service.update_profile(user, payload)


@router.patch("/{user_id}", response_model=UserRead)
async def admin_update_user(
    user_id: uuid.UUID,
    payload: UserAdminUpdate,
    actor: User = Depends(require_permissions("users:write")),
    db: AsyncSession = Depends(get_db),
) -> User:
    service = UserService(db)
    return await service.admin_update(user_id, payload, actor)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permissions("users:delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = UserService(db)
    await service.deactivate(user_id, actor)


@router.get("/me/api-keys", response_model=list[APIKeyRead])
async def list_my_api_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    service = UserService(db)
    return await service.list_api_keys(user)


@router.post("/me/api-keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_my_api_key(
    payload: APIKeyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    service = UserService(db)
    _user, raw_key, api_key = await service.create_api_key(user, payload)
    return {
        "id": api_key.id,
        "name": api_key.name,
        "raw_key": raw_key,
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at,
    }


@router.delete("/me/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_api_key(
    api_key_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    service = UserService(db)
    await service.revoke_api_key(user, api_key_id)