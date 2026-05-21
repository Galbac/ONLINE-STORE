from uuid import uuid4
from urllib.parse import quote

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


class ExternalStorageProvider:
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
        external_provider: ExternalStorageProvider | None = None,
    ) -> None:
        self.media_settings = media_settings
        self.local_provider = local_provider or LocalStorageProvider(media_settings)
        self.external_provider = external_provider or ExternalStorageProvider(media_settings)

    async def save_file(self, *, stored_filename: str, content: bytes) -> tuple[str, str]:
        if self.media_settings.storage == "local":
            return await self.local_provider.save(stored_filename=stored_filename, content=content), "local"
        if self.media_settings.storage == "external":
            return await self.external_provider.save(stored_filename=stored_filename, content=content), "external"
        raise UploadStorageError

    async def delete_file(self, *, storage_type: str, stored_filename: str) -> None:
        if storage_type == "local":
            await self.local_provider.delete(stored_filename=stored_filename)
            return
        if storage_type == "external":
            await self.external_provider.delete(stored_filename=stored_filename)
            return
        raise UploadStorageError

    async def health_check(self, *, check_write: bool = False) -> dict:
        if self.media_settings.storage == "local":
            return await self.local_provider.health_check(check_write=check_write)
        if self.media_settings.storage == "external":
            return await self.external_provider.health_check(check_write=check_write)
        raise UploadStorageError
