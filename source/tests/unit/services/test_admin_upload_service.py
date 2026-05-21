from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from source.config.settings import MediaSettings, settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.upload import (
    UploadFileMissingError,
    UploadFileTooLargeError,
    UploadUnsupportedExtensionError,
    UploadUnsupportedFormatError,
)
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_upload import AdminUploadService
from source.services.storage import StorageService

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 "


class FakeUploadFile:
    def __init__(self, *, filename: str | None, content_type: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


class FakeLocalProvider:
    def __init__(self) -> None:
        self.saved: list[tuple[str, bytes]] = []

    async def save(self, *, stored_filename: str, content: bytes) -> str:
        self.saved.append((stored_filename, content))
        return f"/media/{stored_filename}"


class FakeExternalProvider:
    def __init__(self) -> None:
        self.saved: list[tuple[str, bytes]] = []

    async def save(self, *, stored_filename: str, content: bytes) -> str:
        self.saved.append((stored_filename, content))
        return f"https://cdn.example.com/{stored_filename}"


class FakeUploadRepository:
    def __init__(self) -> None:
        self.created_payload: dict | None = None

    async def create(self, **kwargs):
        self.created_payload = kwargs
        return SimpleNamespace(
            id=1001,
            original_filename=kwargs["original_filename"],
            stored_filename=kwargs["stored_filename"],
            mime_type=kwargs["mime_type"],
            size=kwargs["size"],
            storage_type=kwargs["storage_type"],
            url=kwargs["url"],
            entity_type=kwargs["entity_type"],
            uploaded_by=kwargs["uploaded_by"],
            is_deleted=False,
            created_date=datetime(2026, 5, 12, 10, 0, tzinfo=settings.tz),
        )


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.created_payload: dict | None = None

    async def create(self, *, session, **data):
        self.created_payload = data
        return SimpleNamespace(**data)


def build_media_settings(*, storage: str = "local", max_image_size_mb: int = 5) -> MediaSettings:
    return MediaSettings().model_copy(
        update={
            "storage": storage,
            "root": Path("/tmp/media"),
            "url": "/media",
            "max_image_size_mb": max_image_size_mb,
            "allowed_image_types": "image/jpeg,image/png,image/webp",
            "allowed_image_extensions": ".jpg,.jpeg,.png,.webp",
            "base_url": "https://cdn.example.com",
        },
    )


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(
        id=1,
        role=role,
        email="admin@example.com",
        phone=None,
        is_active=True,
        is_deleted=False,
        is_blocked=False,
    )


async def upload_admin_image(
    *,
    file=None,
    storage: str = "local",
    max_image_size_mb: int = 5,
    user=None,
    upload_repository=None,
    audit_log_repository=None,
    local_provider=None,
    external_provider=None,
):
    media_settings = build_media_settings(storage=storage, max_image_size_mb=max_image_size_mb)
    return await AdminUploadService().upload_image(
        session=object(),
        user=user or build_user(),
        file=file,
        entity_type="product",
        media_settings=media_settings,
        storage_service=StorageService(
            media_settings,
            local_provider=local_provider or FakeLocalProvider(),
            external_provider=external_provider,
        ),
        upload_repository=upload_repository or FakeUploadRepository(),
        permission_service=PermissionService(),
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
    )


@pytest.mark.asyncio
async def test_admin_upload_image_local_success_creates_record() -> None:
    repository = FakeUploadRepository()
    local_provider = FakeLocalProvider()

    response = await upload_admin_image(
        file=FakeUploadFile(filename="apple.png", content_type="image/png", content=PNG_BYTES),
        upload_repository=repository,
        local_provider=local_provider,
    )

    assert response.id == 1001
    assert response.stored_filename.startswith("product/")
    assert response.stored_filename.endswith(".png")
    assert response.original_filename == "apple.png"
    assert repository.created_payload["storage_type"] == "local"
    assert repository.created_payload["uploaded_by"] == 1
    assert local_provider.saved


@pytest.mark.asyncio
async def test_admin_upload_image_external_success() -> None:
    external_provider = FakeExternalProvider()

    response = await upload_admin_image(
        storage="external",
        file=FakeUploadFile(filename="apple.webp", content_type="image/webp", content=WEBP_BYTES),
        external_provider=external_provider,
    )

    assert response.storage_type == "external"
    assert response.url.startswith("https://cdn.example.com/product/")
    assert external_provider.saved


@pytest.mark.asyncio
async def test_admin_upload_image_missing_file_error() -> None:
    with pytest.raises(UploadFileMissingError):
        await upload_admin_image(file=None)


@pytest.mark.asyncio
async def test_admin_upload_image_unsupported_mime_type_error() -> None:
    with pytest.raises(UploadUnsupportedFormatError):
        await upload_admin_image(file=FakeUploadFile(filename="file.gif", content_type="image/gif", content=b"GIF89a"))


@pytest.mark.asyncio
async def test_admin_upload_image_unsupported_extension_error() -> None:
    with pytest.raises(UploadUnsupportedExtensionError):
        await upload_admin_image(file=FakeUploadFile(filename="apple.gif", content_type="image/png", content=PNG_BYTES))


@pytest.mark.asyncio
async def test_admin_upload_image_too_large_error() -> None:
    with pytest.raises(UploadFileTooLargeError):
        await upload_admin_image(
            max_image_size_mb=0,
            file=FakeUploadFile(filename="apple.png", content_type="image/png", content=PNG_BYTES),
        )


@pytest.mark.asyncio
async def test_admin_upload_image_user_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await upload_admin_image(
            user=build_user(role=UserRole.MANAGER),
            file=FakeUploadFile(filename="apple.png", content_type="image/png", content=PNG_BYTES),
        )


@pytest.mark.asyncio
async def test_admin_upload_image_response_does_not_return_physical_path() -> None:
    response = await upload_admin_image(file=FakeUploadFile(filename="apple.png", content_type="image/png", content=PNG_BYTES))

    assert "/tmp/media" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_admin_upload_image_audit_log_created() -> None:
    audit_log_repository = FakeAuditLogRepository()

    await upload_admin_image(
        file=FakeUploadFile(filename="apple.png", content_type="image/png", content=PNG_BYTES),
        audit_log_repository=audit_log_repository,
    )

    assert audit_log_repository.created_payload["event"] == "admin_upload_image_create"
    assert audit_log_repository.created_payload["details"]["file_id"] == 1001
