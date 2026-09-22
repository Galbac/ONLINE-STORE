from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from source.config.settings import MediaSettings
from source.errors.upload import UploadStorageError
from source.services.storage import (
    LocalStorageProvider,
    S3StorageProvider,
    StorageService,
)


@pytest.fixture
def temp_media_root(tmp_path: Path) -> Path:
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir


@pytest.mark.asyncio
async def test_local_storage_provider_save_and_delete(temp_media_root: Path) -> None:
    settings = MediaSettings(
        _env_file=None,
        storage="local",
        root=temp_media_root,
        url="/media",
    )
    provider = LocalStorageProvider(settings)

    url = await provider.save(stored_filename="product/test.webp", content=b"fake-image-bytes")
    assert url == "/media/product/test.webp"
    assert (temp_media_root / "product/test.webp").exists()
    assert (temp_media_root / "product/test.webp").read_bytes() == b"fake-image-bytes"

    await provider.delete(stored_filename="product/test.webp")
    assert not (temp_media_root / "product/test.webp").exists()


@pytest.mark.asyncio
async def test_local_storage_provider_health_check(temp_media_root: Path) -> None:
    settings = MediaSettings(
        _env_file=None,
        storage="local",
        root=temp_media_root,
        url="/media",
    )
    provider = LocalStorageProvider(settings)
    health = await provider.health_check(check_write=True)
    assert health["readable"] is True
    assert health["writable"] is True


@pytest.mark.asyncio
async def test_s3_storage_provider_url_generation() -> None:
    # 1. Custom public URL / CDN
    settings_cdn = MediaSettings(
        _env_file=None,
        storage="s3",
        storage_bucket="my-bucket",
        s3_public_url="https://cdn.example.com",
    )
    provider_cdn = S3StorageProvider(settings_cdn)
    assert provider_cdn._build_public_url("product/123.webp") == "https://cdn.example.com/product/123.webp"

    # 2. Custom S3 endpoint (Yandex / MinIO)
    settings_yc = MediaSettings(
        _env_file=None,
        storage="s3",
        storage_bucket="grocery-media",
        s3_endpoint_url="https://storage.yandexcloud.net",
    )
    provider_yc = S3StorageProvider(settings_yc)
    assert (
        provider_yc._build_public_url("product/item.webp")
        == "https://storage.yandexcloud.net/grocery-media/product/item.webp"
    )

    # 3. Standard AWS S3
    settings_aws = MediaSettings(
        _env_file=None,
        storage="s3",
        storage_bucket="grocery-media",
        storage_region="eu-west-1",
    )
    provider_aws = S3StorageProvider(settings_aws)
    assert (
        provider_aws._build_public_url("product/item.webp")
        == "https://grocery-media.s3.eu-west-1.amazonaws.com/product/item.webp"
    )


@pytest.mark.asyncio
async def test_s3_storage_provider_save_and_delete() -> None:
    settings = MediaSettings(
        _env_file=None,
        storage="s3",
        storage_bucket="test-bucket",
        s3_endpoint_url="https://storage.yandexcloud.net",
        storage_access_key="key",
        storage_secret_key="secret",
    )
    provider = S3StorageProvider(settings)

    mock_boto_client = MagicMock()
    with patch.object(provider, "_get_client", return_value=mock_boto_client):
        url = await provider.save(stored_filename="product/photo.webp", content=b"test-bytes")
        assert url == "https://storage.yandexcloud.net/test-bucket/product/photo.webp"
        mock_boto_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="product/photo.webp",
            Body=b"test-bytes",
            ContentType="image/webp",
            CacheControl="public, max-age=31536000, immutable",
        )

        await provider.delete(stored_filename="product/photo.webp")
        mock_boto_client.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="product/photo.webp",
        )


@pytest.mark.asyncio
async def test_s3_storage_provider_health_check() -> None:
    settings = MediaSettings(
        _env_file=None,
        storage="s3",
        storage_bucket="test-bucket",
    )
    provider = S3StorageProvider(settings)

    mock_boto_client = MagicMock()
    with patch.object(provider, "_get_client", return_value=mock_boto_client):
        health = await provider.health_check(check_write=True)
        assert health["available"] is True
        assert health["writable"] is True
        mock_boto_client.head_bucket.assert_called_once_with(Bucket="test-bucket")


@pytest.mark.asyncio
async def test_storage_service_dispatches_properly(temp_media_root: Path) -> None:
    # 1. Local storage
    local_settings = MediaSettings(_env_file=None, storage="local", root=temp_media_root)
    service_local = StorageService(local_settings)
    url, storage_type = await service_local.save_file(stored_filename="cat/test.webp", content=b"test")
    assert storage_type == "local"
    assert url == "/media/cat/test.webp"

    # 2. S3 storage
    s3_settings = MediaSettings(
        _env_file=None,
        storage="s3",
        storage_bucket="my-bucket",
        s3_public_url="https://cdn.test.com",
    )
    service_s3 = StorageService(s3_settings)
    with patch.object(service_s3.external_provider, "save", return_value="https://cdn.test.com/cat/test.webp") as mock_save:
        url, storage_type = await service_s3.save_file(stored_filename="cat/test.webp", content=b"test")
        assert storage_type == "external"
        assert url == "https://cdn.test.com/cat/test.webp"
        mock_save.assert_called_once()
