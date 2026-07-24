"""
Object Storage service: thin async wrapper over an S3-compatible backend
(AWS S3 or MinIO for local/dev). Every file the platform produces or
accepts — report exports, uploaded attachments, avatars — flows through
here so callers never touch boto3 directly and storage backend swaps
(S3 <-> GCS <-> Azure Blob) stay localized to this one module.
"""
from __future__ import annotations

import io
import mimetypes
import uuid
from datetime import timedelta

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.base import FileStorageError

logger = get_logger(__name__)


class StorageService:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            use_ssl=settings.S3_USE_SSL,
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )
        self.bucket = settings.S3_BUCKET

    def ensure_bucket_exists(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self.bucket)
                logger.info("storage.bucket_created", bucket=self.bucket)
            except (BotoCoreError, ClientError) as exc:
                raise FileStorageError(f"Failed to create bucket '{self.bucket}': {exc}") from exc

    async def upload_bytes(
        self, key: str, data: bytes, content_type: str | None = None, *, metadata: dict[str, str] | None = None
    ) -> str:
        content_type = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=io.BytesIO(data),
                ContentType=content_type,
                Metadata=metadata or {},
            )
            logger.info("storage.upload_completed", key=key, size_bytes=len(data))
            return key
        except (BotoCoreError, ClientError) as exc:
            logger.error("storage.upload_failed", key=key, error=str(exc))
            raise FileStorageError(f"Failed to upload object '{key}'") from exc

    async def upload_user_file(
        self, organization_id: uuid.UUID, filename: str, data: bytes, content_type: str | None = None
    ) -> str:
        safe_name = filename.replace("/", "_").replace("\\", "_")
        key = f"uploads/{organization_id}/{uuid.uuid4()}_{safe_name}"
        return await self.upload_bytes(key, data, content_type)

    async def download_bytes(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            logger.error("storage.download_failed", key=key, error=str(exc))
            raise FileStorageError(f"Failed to download object '{key}'") from exc

    async def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
            logger.info("storage.delete_completed", key=key)
        except (BotoCoreError, ClientError) as exc:
            logger.error("storage.delete_failed", key=key, error=str(exc))
            raise FileStorageError(f"Failed to delete object '{key}'") from exc

    async def generate_presigned_url(self, key: str, *, expires_in: timedelta = timedelta(hours=1)) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=int(expires_in.total_seconds()),
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("storage.presign_failed", key=key, error=str(exc))
            raise FileStorageError(f"Failed to generate presigned URL for '{key}'") from exc

    async def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    async def list_keys(self, prefix: str, *, max_keys: int = 1000) -> list[str]:
        try:
            response = self._client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=max_keys)
            return [obj["Key"] for obj in response.get("Contents", [])]
        except (BotoCoreError, ClientError) as exc:
            logger.error("storage.list_failed", prefix=prefix, error=str(exc))
            raise FileStorageError(f"Failed to list objects with prefix '{prefix}'") from exc