from pathlib import Path

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


class ExternalStorageProvider:
    def __init__(self, media_settings: MediaSettings) -> None:
        self.media_settings = media_settings

    async def save(self, *, stored_filename: str, content: bytes) -> str:
        raise UploadStorageError

    async def delete(self, *, stored_filename: str) -> None:
        raise UploadStorageError


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
