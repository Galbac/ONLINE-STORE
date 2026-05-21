from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.dependencies import require_admin_or_manager
from source.config.settings import MediaSettings, settings
from source.db.models.choises.enum import UserRole
from source.errors.upload import (
    UploadFileMissingError,
    UploadFileTooLargeError,
    UploadInUseError,
    UploadNotFoundError,
    UploadPrivateAccessRequiredError,
    UploadUnsupportedFormatError,
)
from source.schemas.pydantic.upload import UploadFileResponse
from source.services.storage import StorageService
from source.services.upload import UploadService
from source.services.upload_cache import UploadCacheService

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 "


class FakeUploadFile:
    def __init__(self, *, filename: str | None, content_type: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


class FakeUploadRepository:
    def __init__(self, upload=None) -> None:
        self.upload = upload
        self.created_payload: dict | None = None
        self.soft_deleted = False

    async def create(self, **kwargs):
        self.created_payload = kwargs
        self.upload = build_upload(
            file_id=1001,
            original_filename=kwargs["original_filename"],
            stored_filename=kwargs["stored_filename"],
            mime_type=kwargs["mime_type"],
            size=kwargs["size"],
            storage_type=kwargs["storage_type"],
            url=kwargs["url"],
            entity_type=kwargs["entity_type"],
            uploaded_by=kwargs["uploaded_by"],
        )
        return self.upload

    async def get_by_id(self, *, session, file_id: int):
        if self.upload is not None and self.upload.id == file_id:
            return self.upload
        return None

    async def soft_delete(self, *, session, upload, deleted_by: int, deleted_at: datetime):
        upload.is_deleted = True
        upload.deleted_by = deleted_by
        upload.deleted_at = deleted_at
        self.soft_deleted = True
        return upload


class FakeProductImageRepository:
    def __init__(self, in_use: bool = False) -> None:
        self.in_use = in_use

    async def exists_by_file_id(self, *, session, file_id: int) -> bool:
        return self.in_use


class FakeCategoryRepository:
    def __init__(self, in_use: bool = False) -> None:
        self.in_use = in_use

    async def exists_by_image_file_id(self, *, session, file_id: int) -> bool:
        return self.in_use


class FakeLocalProvider:
    def __init__(self) -> None:
        self.saved: list[tuple[str, bytes]] = []
        self.deleted: list[str] = []

    async def save(self, *, stored_filename: str, content: bytes) -> str:
        self.saved.append((stored_filename, content))
        return f"/media/{stored_filename}"

    async def delete(self, *, stored_filename: str) -> None:
        self.deleted.append(stored_filename)


class FakeExternalProvider:
    def __init__(self) -> None:
        self.saved: list[tuple[str, bytes]] = []
        self.deleted: list[str] = []

    async def save(self, *, stored_filename: str, content: bytes) -> str:
        self.saved.append((stored_filename, content))
        return f"https://cdn.example.com/{stored_filename}"

    async def delete(self, *, stored_filename: str) -> None:
        self.deleted.append(stored_filename)


def build_media_settings(*, storage: str = "local", max_image_size_mb: int = 5) -> MediaSettings:
    return MediaSettings().model_copy(
        update={
            "storage": storage,
            "root": Path("/tmp/media"),
            "url": "/media",
            "max_image_size_mb": max_image_size_mb,
            "allowed_image_types": "image/jpeg,image/png,image/webp",
            "base_url": "https://cdn.example.com",
        },
    )


def build_user(*, user_id: int = 1, role: UserRole = UserRole.ADMIN):
    return SimpleNamespace(id=user_id, role=role)


def build_upload(
    *,
    file_id: int = 1001,
    original_filename: str = "apple.png",
    stored_filename: str = "product/safe.png",
    mime_type: str = "image/png",
    size: int = 4,
    storage_type: str = "local",
    url: str = "/media/product/safe.png",
    entity_type: str | None = "product",
    uploaded_by: int = 1,
    is_public: bool = True,
    is_deleted: bool = False,
):
    return SimpleNamespace(
        id=file_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        mime_type=mime_type,
        size=size,
        storage_type=storage_type,
        url=url,
        entity_type=entity_type,
        uploaded_by=uploaded_by,
        is_public=is_public,
        is_deleted=is_deleted,
        created_date=datetime(2026, 5, 12, 10, 0, tzinfo=settings.tz),
        deleted_at=None,
        deleted_by=None,
    )


@pytest.mark.asyncio
async def test_upload_image_local_success_creates_record() -> None:
    local_provider = FakeLocalProvider()
    repository = FakeUploadRepository()
    response = await UploadService().upload_image(
        session=object(),
        media_settings=build_media_settings(),
        storage_service=StorageService(build_media_settings(), local_provider=local_provider),
        upload_repository=repository,
        user=build_user(),
        file=FakeUploadFile(filename="apple.png", content_type="image/png", content=PNG_BYTES),
        entity_type="product",
    )

    assert response.id == 1001
    assert response.url.startswith("/media/product/")
    assert repository.created_payload["original_filename"] == "apple.png"
    assert repository.created_payload["storage_type"] == "local"
    assert local_provider.saved[0][0].startswith("product/")


@pytest.mark.asyncio
async def test_upload_image_external_success() -> None:
    external_provider = FakeExternalProvider()
    response = await UploadService().upload_image(
        session=object(),
        media_settings=build_media_settings(storage="external"),
        storage_service=StorageService(build_media_settings(storage="external"), external_provider=external_provider),
        upload_repository=FakeUploadRepository(),
        user=build_user(),
        file=FakeUploadFile(filename="apple.webp", content_type="image/webp", content=WEBP_BYTES),
        entity_type="product",
    )

    assert response.storage_type == "external"
    assert response.url.startswith("https://cdn.example.com/product/")
    assert external_provider.saved


@pytest.mark.asyncio
async def test_upload_image_missing_file_error() -> None:
    with pytest.raises(UploadFileMissingError):
        await UploadService().upload_image(
            session=object(),
            media_settings=build_media_settings(),
            storage_service=StorageService(build_media_settings(), local_provider=FakeLocalProvider()),
            upload_repository=FakeUploadRepository(),
            user=build_user(),
            file=None,
            entity_type=None,
        )


@pytest.mark.asyncio
async def test_upload_image_unsupported_mime_type_error() -> None:
    with pytest.raises(UploadUnsupportedFormatError):
        await UploadService().upload_image(
            session=object(),
            media_settings=build_media_settings(),
            storage_service=StorageService(build_media_settings(), local_provider=FakeLocalProvider()),
            upload_repository=FakeUploadRepository(),
            user=build_user(),
            file=FakeUploadFile(filename="file.gif", content_type="image/gif", content=b"data"),
            entity_type=None,
        )


@pytest.mark.asyncio
async def test_upload_image_too_large_error() -> None:
    with pytest.raises(UploadFileTooLargeError):
        await UploadService().upload_image(
            session=object(),
            media_settings=build_media_settings(max_image_size_mb=0),
            storage_service=StorageService(build_media_settings(), local_provider=FakeLocalProvider()),
            upload_repository=FakeUploadRepository(),
            user=build_user(),
            file=FakeUploadFile(filename="apple.png", content_type="image/png", content=PNG_BYTES),
            entity_type=None,
        )


@pytest.mark.asyncio
async def test_upload_requires_admin_or_manager() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_or_manager(SimpleNamespace(role=UserRole.CUSTOMER))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_file_local_success_soft_deletes_record() -> None:
    upload = build_upload()
    repository = FakeUploadRepository(upload)
    local_provider = FakeLocalProvider()

    await UploadService().delete_file(
        session=object(),
        redis_service=FakeRedisService(),
        storage_service=StorageService(build_media_settings(), local_provider=local_provider),
        upload_cache_service=UploadCacheService(),
        upload_repository=repository,
        product_image_repository=FakeProductImageRepository(),
        category_repository=FakeCategoryRepository(),
        user=build_user(),
        file_id=1001,
    )

    assert local_provider.deleted == ["product/safe.png"]
    assert repository.soft_deleted is True
    assert upload.is_deleted is True


@pytest.mark.asyncio
async def test_delete_file_external_success() -> None:
    upload = build_upload(storage_type="external", url="https://cdn.example.com/product/safe.png")
    external_provider = FakeExternalProvider()

    await UploadService().delete_file(
        session=object(),
        redis_service=FakeRedisService(),
        storage_service=StorageService(build_media_settings(storage="external"), external_provider=external_provider),
        upload_cache_service=UploadCacheService(),
        upload_repository=FakeUploadRepository(upload),
        product_image_repository=FakeProductImageRepository(),
        category_repository=FakeCategoryRepository(),
        user=build_user(),
        file_id=1001,
    )

    assert external_provider.deleted == ["product/safe.png"]


@pytest.mark.asyncio
async def test_delete_file_not_found_error() -> None:
    with pytest.raises(UploadNotFoundError):
        await UploadService().delete_file(
            session=object(),
            redis_service=FakeRedisService(),
            storage_service=StorageService(build_media_settings(), local_provider=FakeLocalProvider()),
            upload_cache_service=UploadCacheService(),
            upload_repository=FakeUploadRepository(),
            product_image_repository=FakeProductImageRepository(),
            category_repository=FakeCategoryRepository(),
            user=build_user(),
            file_id=1001,
        )


@pytest.mark.asyncio
async def test_delete_file_in_use_error() -> None:
    with pytest.raises(UploadInUseError):
        await UploadService().delete_file(
            session=object(),
            redis_service=FakeRedisService(),
            storage_service=StorageService(build_media_settings(), local_provider=FakeLocalProvider()),
            upload_cache_service=UploadCacheService(),
            upload_repository=FakeUploadRepository(build_upload()),
            product_image_repository=FakeProductImageRepository(in_use=True),
            category_repository=FakeCategoryRepository(),
            user=build_user(),
            file_id=1001,
        )


@pytest.mark.asyncio
async def test_get_file_detail_success_and_cache_set() -> None:
    redis_service = FakeRedisService()
    response = await UploadService().get_file_detail(
        session=object(),
        redis_service=redis_service,
        upload_cache_service=UploadCacheService(),
        upload_repository=FakeUploadRepository(build_upload()),
        file_id=1001,
    )

    assert response.id == 1001
    assert "stored_filename" not in response.model_dump()
    assert redis_service.ttls["uploads:detail:1001"] == settings.media.detail_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_file_detail_from_cache() -> None:
    redis_service = FakeRedisService()
    cached = UploadFileResponse(
        id=1001,
        url="/media/product/safe.png",
        original_filename="apple.png",
        mime_type="image/png",
        size=4,
        storage_type="local",
        entity_type="product",
        created_at=datetime(2026, 5, 12, 10, 0, tzinfo=settings.tz),
    )
    redis_service.values["uploads:detail:1001"] = cached.model_dump_json()

    response = await UploadService().get_file_detail(
        session=object(),
        redis_service=redis_service,
        upload_cache_service=UploadCacheService(),
        upload_repository=FakeUploadRepository(),
        file_id=1001,
    )

    assert response == cached


@pytest.mark.asyncio
async def test_get_file_detail_not_found_and_deleted_errors() -> None:
    with pytest.raises(UploadNotFoundError):
        await UploadService().get_file_detail(
            session=object(),
            redis_service=FakeRedisService(),
            upload_cache_service=UploadCacheService(),
            upload_repository=FakeUploadRepository(),
            file_id=1001,
        )
    with pytest.raises(UploadNotFoundError):
        await UploadService().get_file_detail(
            session=object(),
            redis_service=FakeRedisService(),
            upload_cache_service=UploadCacheService(),
            upload_repository=FakeUploadRepository(build_upload(is_deleted=True)),
            file_id=1001,
        )


@pytest.mark.asyncio
async def test_get_private_file_requires_authentication() -> None:
    with pytest.raises(UploadPrivateAccessRequiredError):
        await UploadService().get_file_detail(
            session=object(),
            redis_service=FakeRedisService(),
            upload_cache_service=UploadCacheService(),
            upload_repository=FakeUploadRepository(build_upload(is_public=False)),
            file_id=1001,
        )
