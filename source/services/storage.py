from __future__ import annotations

import asyncio
from mimetypes import guess_type
from urllib.parse import quote
from uuid import uuid4

from source.config.settings import MediaSettings
from source.errors.upload import UploadStorageError


class LocalStorageProvider:
    def __init__(self, media_settings: MediaSettings) -> None:
        self.media_settings = media_settings

    async def save(self, *, stored_filename: str, content: bytes) -> str:
        try:
            destination = self.media_settings.root / stored_filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        except OSError as error:
            raise UploadStorageError from error

        if self.media_settings.base_url:
            base = self.media_settings.base_url.rstrip("/")
            path = self.media_settings.url.strip("/")
            return f"{base}/{path}/{stored_filename}"
        return f"{self.media_settings.url.rstrip('/')}/{stored_filename}"

    async def delete(self, *, stored_filename: str) -> None:
        try:
            path = self.media_settings.root / stored_filename
            path.unlink(missing_ok=True)
        except OSError as error:
            raise UploadStorageError from error

    async def health_check(self, *, check_write: bool = False) -> dict:
        root = self.media_settings.root
        if not root or not root.exists() or not root.is_dir():
            raise UploadStorageError
        readable = root.stat() is not None
        writable = False
        if check_write:
            temp_path = root / f".health-{uuid4().hex}.tmp"
            try:
                temp_path.write_text("ok", encoding="utf-8")
                writable = True
            except OSError as error:
                raise UploadStorageError from error
            finally:
                temp_path.unlink(missing_ok=True)
        return {"readable": readable, "writable": writable if check_write else None}


class S3StorageProvider:
    """
    S3 / MinIO Storage Provider.
    Совместим с AWS S3, MinIO, Yandex Cloud Object Storage, Selectel S3 и другими S3-хранилищами.
    """

    def __init__(self, media_settings: MediaSettings) -> None:
        self.media_settings = media_settings
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:
                raise UploadStorageError("boto3 package is required for S3 storage") from exc

            config = Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            )
            client_kwargs = {
                "service_name": "s3",
                "aws_access_key_id": self.media_settings.effective_access_key or None,
                "aws_secret_access_key": self.media_settings.effective_secret_key or None,
                "region_name": self.media_settings.effective_region or None,
                "use_ssl": self.media_settings.s3_use_ssl,
                "verify": self.media_settings.s3_verify_ssl,
                "config": config,
            }
            if self.media_settings.s3_endpoint_url:
                client_kwargs["endpoint_url"] = self.media_settings.s3_endpoint_url

            self._client = boto3.client(**client_kwargs)
        return self._client

    def _build_public_url(self, stored_filename: str) -> str:
        encoded_filename = quote(stored_filename)
        if self.media_settings.s3_public_url:
            return f"{self.media_settings.s3_public_url.rstrip('/')}/{encoded_filename}"
        if self.media_settings.base_url:
            return f"{self.media_settings.base_url.rstrip('/')}/{encoded_filename}"

        bucket = self.media_settings.effective_bucket
        endpoint = self.media_settings.s3_endpoint_url
        if endpoint:
            return f"{endpoint.rstrip('/')}/{bucket}/{encoded_filename}"

        region = self.media_settings.effective_region
        if region and region != "us-east-1":
            return f"https://{bucket}.s3.{region}.amazonaws.com/{encoded_filename}"
        return f"https://{bucket}.s3.amazonaws.com/{encoded_filename}"

    async def save(self, *, stored_filename: str, content: bytes) -> str:
        bucket = self.media_settings.effective_bucket
        if not bucket:
            raise UploadStorageError("S3 bucket name is not configured")

        mime_type, _ = guess_type(stored_filename)
        content_type = mime_type or "application/octet-stream"

        def _upload() -> None:
            client = self._get_client()
            client.put_object(
                Bucket=bucket,
                Key=stored_filename,
                Body=content,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )

        try:
            await asyncio.to_thread(_upload)
        except Exception as error:
            raise UploadStorageError from error

        return self._build_public_url(stored_filename)

    async def delete(self, *, stored_filename: str) -> None:
        bucket = self.media_settings.effective_bucket
        if not bucket:
            return

        def _delete() -> None:
            client = self._get_client()
            client.delete_object(Bucket=bucket, Key=stored_filename)

        try:
            await asyncio.to_thread(_delete)
        except Exception as error:
            raise UploadStorageError from error

    async def health_check(self, *, check_write: bool = False) -> dict:
        bucket = self.media_settings.effective_bucket
        if not bucket:
            raise UploadStorageError("S3 bucket is not configured")

        def _check() -> dict:
            client = self._get_client()
            client.head_bucket(Bucket=bucket)
            writable = False
            if check_write:
                temp_key = f".health-{uuid4().hex}.tmp"
                client.put_object(Bucket=bucket, Key=temp_key, Body=b"ok")
                client.delete_object(Bucket=bucket, Key=temp_key)
                writable = True
            return {"available": True, "writable": writable if check_write else None}

        try:
            return await asyncio.to_thread(_check)
        except Exception as error:
            raise UploadStorageError from error


class ExternalStorageProvider:
    """
    Fallback/Mock External Storage Provider.
    """

    def __init__(self, media_settings: MediaSettings) -> None:
        self.media_settings = media_settings

    async def save(self, *, stored_filename: str, content: bytes) -> str:
        if not self.media_settings.base_url:
            raise UploadStorageError
        return f"{self.media_settings.base_url.rstrip('/')}/{quote(stored_filename)}"

    async def delete(self, *, stored_filename: str) -> None:
        return None

    async def health_check(self, *, check_write: bool = False) -> dict:
        if not self.media_settings.storage_bucket:
            raise UploadStorageError
        return {"available": True}


class StorageService:
    def __init__(
        self,
        media_settings: MediaSettings,
        local_provider: LocalStorageProvider | None = None,
        external_provider: ExternalStorageProvider | S3StorageProvider | None = None,
    ) -> None:
        self.media_settings = media_settings
        self.local_provider = local_provider or LocalStorageProvider(media_settings)
        if external_provider is not None:
            self.external_provider = external_provider
        elif media_settings.storage.lower() in ("s3", "minio"):
            self.external_provider = S3StorageProvider(media_settings)
        else:
            self.external_provider = ExternalStorageProvider(media_settings)

    async def save_file(self, *, stored_filename: str, content: bytes) -> tuple[str, str]:
        storage = self.media_settings.storage.lower()
        if storage == "local":
            return await self.local_provider.save(stored_filename=stored_filename, content=content), "local"
        if storage in ("external", "s3", "minio"):
            return await self.external_provider.save(stored_filename=stored_filename, content=content), "external"
        raise UploadStorageError

    async def delete_file(self, *, storage_type: str, stored_filename: str) -> None:
        normalized_storage_type = storage_type.lower()
        if normalized_storage_type == "local":
            await self.local_provider.delete(stored_filename=stored_filename)
            return
        if normalized_storage_type in ("external", "s3", "minio"):
            await self.external_provider.delete(stored_filename=stored_filename)
            return
        raise UploadStorageError

    async def health_check(self, *, check_write: bool = False) -> dict:
        storage = self.media_settings.storage.lower()
        if storage == "local":
            return await self.local_provider.health_check(check_write=check_write)
        if storage in ("external", "s3", "minio"):
            return await self.external_provider.health_check(check_write=check_write)
        raise UploadStorageError
