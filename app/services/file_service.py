"""File attachment service: upload, metadata retrieval, presigned download, deletion."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.base import NotFoundError, ValidationError
from app.models.files import FileAttachment
from app.models.identity import User
from app.repositories.base import BaseRepository
from app.services.storage_services import StorageService

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "text/csv",
    "application/json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class FileAttachmentRepository(BaseRepository[FileAttachment]):
    model = FileAttachment


class FileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.files = FileAttachmentRepository(session)
        self.storage = StorageService()

    async def upload(
        self,
        user: User,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> FileAttachment:
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            raise ValidationError(f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB")
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationError(f"File type '{content_type}' is not permitted")

        storage_key = await self.storage.upload_user_file(user.organization_id, filename, content, content_type)

        attachment = await self.files.create(
            id=uuid.uuid4(),
            organization_id=user.organization_id,
            uploaded_by_id=user.id,
            original_filename=filename,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(content),
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return attachment

    async def get_with_download_url(self, file_id: uuid.UUID, organization_id: uuid.UUID) -> tuple[FileAttachment, str]:
        attachment = await self.files.get(file_id)
        if attachment is None or attachment.organization_id != organization_id:
            raise NotFoundError("File not found")
        url = await self.storage.generate_presigned_url(attachment.storage_key)
        return attachment, url

    async def list_for_resource(self, organization_id: uuid.UUID, resource_type: str, resource_id: str) -> list[FileAttachment]:
        return await self.files.list(
            organization_id=organization_id, resource_type=resource_type, resource_id=resource_id
        )

    async def delete(self, file_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        attachment = await self.files.get(file_id)
        if attachment is None or attachment.organization_id != organization_id:
            raise NotFoundError("File not found")
        await self.storage.delete(attachment.storage_key)
        await self.files.delete(attachment)