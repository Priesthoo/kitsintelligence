"""File upload/download/list/delete endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permissions
from app.models.identity import User
from app.schemas.files import FileAttachmentRead, FileAttachmentWithUrl
from app.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("", response_model=FileAttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    resource_type: str | None = Form(default=None),
    resource_id: str | None = Form(default=None),
    user: User = Depends(require_permissions("files:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = FileService(db)
    content = await file.read()
    return await service.upload(
        user,
        file.filename or "unnamed",
        content,
        file.content_type or "application/octet-stream",
        resource_type=resource_type,
        resource_id=resource_id,
    )


@router.get("/{file_id}", response_model=FileAttachmentWithUrl)
async def get_file(
    file_id: uuid.UUID,
    user: User = Depends(require_permissions("files:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = FileService(db)
    attachment, url = await service.get_with_download_url(file_id, user.organization_id)
    return {
        "id": attachment.id,
        "original_filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "resource_type": attachment.resource_type,
        "resource_id": attachment.resource_id,
        "created_at": attachment.created_at,
        "download_url": url,
    }


@router.get("", response_model=list[FileAttachmentRead])
async def list_files_for_resource(
    resource_type: str,
    resource_id: str,
    user: User = Depends(require_permissions("files:read")),
    db: AsyncSession = Depends(get_db),
) -> list:
    service = FileService(db)
    return await service.list_for_resource(user.organization_id, resource_type, resource_id)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: uuid.UUID,
    user: User = Depends(require_permissions("files:delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = FileService(db)
    await service.delete(file_id, user.organization_id)