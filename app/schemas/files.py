"""DTOs for the File Attachment module."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    resource_type: str | None
    resource_id: str | None
    created_at: datetime


class FileAttachmentWithUrl(FileAttachmentRead):
    download_url: str