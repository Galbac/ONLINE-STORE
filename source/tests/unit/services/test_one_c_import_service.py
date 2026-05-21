from datetime import datetime
import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.integration import import_one_c_categories, import_one_c_products
from source.api.dependencies import verify_one_c_token
from source.config.settings import settings
from source.schemas.pydantic.one_c import (
    OneCCategoryImportItem,
    OneCCategoryImportRequest,
    OneCImageImportItem,
    OneCImageImportRequest,
    OneCPriceImportItem,
    OneCPriceImportRequest,
    OneCProductImportItem,
    OneCProductImportRequest,
    OneCStockImportItem,
    OneCStockImportRequest,
)
from source.services.admin_dashboard_cache import AdminDashboardCacheService
from source.services.admin_product_cache import AdminProductCacheService
from source.services.admin_category_cache import AdminCategoryCacheService
from source.services.cart_cache import CartCacheService
from source.services.category_cache import CategoryCacheService
from source.services.one_c import CategorySyncService, ImageDownloadService, IntegrationLogService, OneCImportService, ProductImageSyncService, ProductPriceSyncService, ProductStockSyncService, ProductSyncService, SlugService
from source.services.product_cache import ProductCacheService
from source.services.stock import StockMovementService


class FakeRedisService:
    def __init__(self) -> None:
        self.deleted_patterns: list[str] = []
        self.deleted: list[str] = []

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeCategoryRepository:
    def __init__(self, categories=None) -> None:
        self.categories = categories or []
        self.next_id = max([category.id for category in self.categories], default=0) + 1

    async def get_by_external_1c_ids(self, *, session, external_1c_ids: set[str]):
        return [
            category
            for category in self.categories
            if category.external_1c_id in external_1c_ids
        ]

    async def get_parent_map_by_external_ids(self, *, session, external_1c_ids: set[str]):
        return {
            category.external_1c_id: category
            for category in await self.get_by_external_1c_ids(session=session, external_1c_ids=external_1c_ids)
            if category.external_1c_id is not None
        }

    async def get_by_slugs(self, *, session, slugs: set[str]):
        return [category for category in self.categories if category.slug in slugs]

    async def bulk_create(self, *, session, items: list[dict]):
        created = []
        for item in items:
            category = build_category(category_id=self.next_id, **item)
            self.next_id += 1
            self.categories.append(category)
            created.append(category)
        return created

    async def bulk_update(self, *, session, categories: list):
        return categories


class FakeProductRepository:
    def __init__(self, products=None) -> None:
        self.products = products or []
        self.next_id = max([product.id for product in self.products], default=0) + 1

    async def get_by_external_1c_ids(self, *, session, external_1c_ids: set[str]):
        return [
            product
            for product in self.products
            if product.external_1c_id in external_1c_ids
        ]

    async def get_by_slugs(self, *, session, slugs: set[str]):
        return [product for product in self.products if product.slug in slugs]

    async def bulk_create(self, *, session, items: list[dict]):
        created = []
        for item in items:
            product = build_product(product_id=self.next_id, **item)
            self.next_id += 1
            self.products.append(product)
            created.append(product)
        return created

    async def bulk_update(self, *, session, products: list):
        return products

    async def bulk_update_prices(self, *, session, products: list):
        return products

    async def bulk_update_stocks(self, *, session, products: list):
        return products


class FakeProductPriceHistoryRepository:
    def __init__(self) -> None:
        self.items: list[dict] = []

    async def bulk_create(self, *, session, items: list[dict]):
        self.items.extend(items)
        return [SimpleNamespace(id=index + 1, **item) for index, item in enumerate(items)]


class FakeProductImageRepository:
    def __init__(self, images=None) -> None:
        self.images = images or []
        self.next_id = max([image.id for image in self.images], default=0) + 1

    async def get_active_models_by_product_id(self, *, session, product_id: int):
        return [
            image
            for image in self.images
            if image.product_id == product_id and not image.is_deleted
        ]

    async def get_by_external_1c_id(self, *, session, image_external_1c_id: str):
        return next(
            (
                image
                for image in self.images
                if image.image_external_1c_id == image_external_1c_id and not image.is_deleted
            ),
            None,
        )

    async def unset_main_by_product_id(self, *, session, product_id: int):
        for image in self.images:
            if image.product_id == product_id and not image.is_deleted:
                image.is_main = False

    async def create(
        self,
        *,
        session,
        product_id: int,
        file_id: int | None,
        url: str,
        sort_order: int,
        is_main: bool,
        image_external_1c_id: str | None = None,
        external_url: str | None = None,
    ):
        image = build_product_image(
            image_id=self.next_id,
            product_id=product_id,
            file_id=file_id,
            url=url,
            sort_order=sort_order,
            is_main=is_main,
            image_external_1c_id=image_external_1c_id,
            external_url=external_url,
        )
        self.next_id += 1
        self.images.append(image)
        return image

    async def update(self, *, session, image, sort_order: int, is_main: bool):
        image.sort_order = sort_order
        image.is_main = is_main
        return image


class FakeUploadRepository:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.next_id = 1

    async def create(self, *, session, **data):
        upload = SimpleNamespace(id=self.next_id, **data)
        self.next_id += 1
        self.items.append(data)
        return upload


class FakeStorageService:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def save_file(self, *, stored_filename: str, content: bytes):
        self.saved.append({"stored_filename": stored_filename, "content": content})
        return f"/media/{stored_filename}", "local"


class FakeImageDownloadService:
    def __init__(self, *, content: bytes | None = None, mime_type: str = "image/png", filename: str = "apple.png") -> None:
        self.content = content or build_png_content()
        self.mime_type = mime_type
        self.filename = filename

    async def download(self, *, image_url: str, max_size_bytes: int):
        return self.content, self.mime_type, self.filename


class FakeStockMovementRepository:
    def __init__(self) -> None:
        self.items: list[dict] = []

    async def bulk_create(self, *, session, items: list[dict]):
        self.items.extend(items)
        return [SimpleNamespace(id=index + 1, **item) for index, item in enumerate(items)]


class FakeIntegrationLogRepository:
    def __init__(self) -> None:
        self.logs: list[dict] = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=len(self.logs), **data)


def build_category(
    *,
    category_id: int = 1,
    external_1c_id: str = "cat-001",
    name: str = "Фрукты",
    slug: str = "frukty",
    parent_id: int | None = None,
    sort_order: int = 0,
    is_active: bool = True,
    sync_status: str | None = "synced",
    last_sync_at=None,
):
    return SimpleNamespace(
        id=category_id,
        external_1c_id=external_1c_id,
        name=name,
        slug=slug,
        parent_id=parent_id,
        sort_order=sort_order,
        is_active=is_active,
        sync_status=sync_status,
        last_sync_at=last_sync_at,
    )


def build_product(
    *,
    product_id: int = 1,
    external_1c_id: str = "prod-001",
    name: str = "Яблоки",
    slug: str = "yabloki",
    article: str | None = None,
    barcode: str | None = None,
    category_id: int | None = None,
    unit: str = "kg",
    product_type: str = "weight",
    quantity_step="0.5",
    min_quantity="0.5",
    price="0",
    old_price=None,
    currency: str = "RUB",
    price_updated_at=None,
    stock_quantity="0",
    reserved_quantity="0",
    stock_updated_at=None,
    low_stock_threshold="5",
    is_active: bool = True,
    is_available: bool = True,
    sync_status: str | None = "synced",
    last_sync_at=None,
    source: str | None = "1c",
    description: str | None = None,
    meta_title: str | None = None,
    meta_description: str | None = None,
):
    return SimpleNamespace(
        id=product_id,
        external_1c_id=external_1c_id,
        name=name,
        slug=slug,
        article=article,
        barcode=barcode,
        category_id=category_id,
        unit=unit,
        product_type=product_type,
        quantity_step=quantity_step,
        min_quantity=min_quantity,
        price=price,
        old_price=old_price,
        currency=currency,
        price_updated_at=price_updated_at,
        stock_quantity=stock_quantity,
        reserved_quantity=reserved_quantity,
        stock_updated_at=stock_updated_at,
        low_stock_threshold=low_stock_threshold,
        is_active=is_active,
        is_available=is_available,
        sync_status=sync_status,
        last_sync_at=last_sync_at,
        source=source,
        description=description,
        meta_title=meta_title,
        meta_description=meta_description,
    )


def build_product_image(
    *,
    image_id: int = 1,
    product_id: int = 1,
    file_id: int | None = None,
    image_external_1c_id: str | None = "img-001",
    external_url: str | None = None,
    url: str = "https://cdn.example.com/apple.png",
    sort_order: int = 0,
    is_main: bool = False,
    is_deleted: bool = False,
):
    return SimpleNamespace(
        id=image_id,
        product_id=product_id,
        file_id=file_id,
        image_external_1c_id=image_external_1c_id,
        external_url=external_url,
        url=url,
        sort_order=sort_order,
        is_main=is_main,
        is_deleted=is_deleted,
    )


def build_png_content() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"0" * 16


def build_request(*items) -> OneCCategoryImportRequest:
    return OneCCategoryImportRequest(items=list(items))


def build_product_request(*items) -> OneCProductImportRequest:
    return OneCProductImportRequest(items=list(items))


def build_product_item(**kwargs) -> OneCProductImportItem:
    data = {
        "external_1c_id": "prod-001",
        "name": "Яблоки красные",
        "sku": "APL-001",
        "barcode": "4600000000001",
        "category_external_1c_id": "cat-001",
        "unit": "kg",
        "product_type": "weight",
        "quantity_step": "0.5",
        "min_quantity": "0.5",
        "is_active": True,
        "is_available": True,
    }
    data.update(kwargs)
    return OneCProductImportItem(**data)


def build_price_request(*items) -> OneCPriceImportRequest:
    return OneCPriceImportRequest(items=list(items))


def build_price_item(**kwargs) -> OneCPriceImportItem:
    data = {
        "product_external_1c_id": "prod-001",
        "price": "150.00",
        "old_price": "180.00",
        "currency": "RUB",
    }
    data.update(kwargs)
    return OneCPriceImportItem(**data)


def build_stock_request(*items) -> OneCStockImportRequest:
    return OneCStockImportRequest(items=list(items))


def build_stock_item(**kwargs) -> OneCStockImportItem:
    data = {
        "product_external_1c_id": "prod-001",
        "stock_quantity": "30.5",
        "reserved_quantity": "2.0",
        "warehouse_external_1c_id": "wh-001",
    }
    data.update(kwargs)
    return OneCStockImportItem(**data)


def build_image_request(*items) -> OneCImageImportRequest:
    return OneCImageImportRequest(items=list(items))


def build_image_item(**kwargs) -> OneCImageImportItem:
    data = {
        "product_external_1c_id": "prod-001",
        "image_external_1c_id": "img-001",
        "image_url": "https://1c.example.com/images/apple.png",
        "sort_order": 1,
        "is_main": True,
    }
    data.update(kwargs)
    return OneCImageImportItem(**data)


async def import_categories(*, data, repository=None, redis_service=None, integration_log_repository=None, commiter=None):
    return await OneCImportService().import_categories(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        data=data,
        commiter=commiter or FakeCommiter(),
        category_repository=repository or FakeCategoryRepository(),
        integration_log_repository=integration_log_repository or FakeIntegrationLogRepository(),
        category_sync_service=CategorySyncService(),
        integration_log_service=IntegrationLogService(),
        category_cache_service=CategoryCacheService(),
        admin_category_cache_service=AdminCategoryCacheService(),
        product_cache_service=ProductCacheService(),
    )


async def import_products(
    *,
    data,
    product_repository=None,
    category_repository=None,
    redis_service=None,
    integration_log_repository=None,
    commiter=None,
):
    return await OneCImportService().import_products(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        data=data,
        commiter=commiter or FakeCommiter(),
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository([build_category()]),
        integration_log_repository=integration_log_repository or FakeIntegrationLogRepository(),
        product_sync_service=ProductSyncService(),
        slug_service=SlugService(),
        integration_log_service=IntegrationLogService(),
        product_cache_service=ProductCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
        category_cache_service=CategoryCacheService(),
    )


async def import_prices(
    *,
    data,
    product_repository=None,
    history_repository=None,
    redis_service=None,
    integration_log_repository=None,
    commiter=None,
):
    return await OneCImportService().import_prices(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        data=data,
        commiter=commiter or FakeCommiter(),
        product_repository=product_repository or FakeProductRepository([build_product(price="100.00")]),
        product_price_history_repository=history_repository or FakeProductPriceHistoryRepository(),
        integration_log_repository=integration_log_repository or FakeIntegrationLogRepository(),
        product_price_sync_service=ProductPriceSyncService(),
        integration_log_service=IntegrationLogService(),
        product_cache_service=ProductCacheService(),
        cart_cache_service=CartCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
    )


async def import_stocks(
    *,
    data,
    product_repository=None,
    stock_movement_repository=None,
    redis_service=None,
    integration_log_repository=None,
    commiter=None,
):
    return await OneCImportService().import_stocks(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        data=data,
        commiter=commiter or FakeCommiter(),
        product_repository=product_repository or FakeProductRepository([build_product(stock_quantity="10.0")]),
        stock_movement_repository=stock_movement_repository or FakeStockMovementRepository(),
        integration_log_repository=integration_log_repository or FakeIntegrationLogRepository(),
        product_stock_sync_service=ProductStockSyncService(),
        stock_movement_service=StockMovementService(),
        integration_log_service=IntegrationLogService(),
        product_cache_service=ProductCacheService(),
        cart_cache_service=CartCacheService(),
        admin_dashboard_cache_service=AdminDashboardCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
    )


async def import_images(
    *,
    data,
    product_repository=None,
    product_image_repository=None,
    upload_repository=None,
    storage_service=None,
    image_download_service=None,
    redis_service=None,
    integration_log_repository=None,
    commiter=None,
):
    return await OneCImportService().import_images(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        data=data,
        commiter=commiter or FakeCommiter(),
        product_repository=product_repository or FakeProductRepository([build_product()]),
        product_image_repository=product_image_repository or FakeProductImageRepository(),
        upload_repository=upload_repository or FakeUploadRepository(),
        integration_log_repository=integration_log_repository or FakeIntegrationLogRepository(),
        product_image_sync_service=ProductImageSyncService(),
        image_download_service=image_download_service or FakeImageDownloadService(),
        storage_service=storage_service or FakeStorageService(),
        integration_log_service=IntegrationLogService(),
        product_cache_service=ProductCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
    )


@pytest.mark.asyncio
async def test_one_c_import_categories_creates_new_categories() -> None:
    repository = FakeCategoryRepository()

    response = await import_categories(
        repository=repository,
        data=build_request(
            OneCCategoryImportItem(external_1c_id="cat-001", name="Фрукты", slug="frukty"),
        ),
    )

    assert response.created == 1
    assert response.updated == 0
    assert repository.categories[0].external_1c_id == "cat-001"
    assert repository.categories[0].sync_status == "synced"
    assert repository.categories[0].last_sync_at is not None


@pytest.mark.asyncio
async def test_one_c_import_categories_updates_existing_categories() -> None:
    category = build_category(name="Старое", slug="staroe")
    repository = FakeCategoryRepository([category])

    response = await import_categories(
        repository=repository,
        data=build_request(
            OneCCategoryImportItem(external_1c_id="cat-001", name="Новое", slug="novoe", is_active=False, sort_order=10),
        ),
    )

    assert response.created == 0
    assert response.updated == 1
    assert category.name == "Новое"
    assert category.slug == "novoe"
    assert category.is_active is False
    assert category.sort_order == 10


@pytest.mark.asyncio
async def test_one_c_import_categories_repeated_import_does_not_create_duplicates() -> None:
    repository = FakeCategoryRepository()
    data = build_request(OneCCategoryImportItem(external_1c_id="cat-001", name="Фрукты", slug="frukty"))

    first = await import_categories(repository=repository, data=data)
    second = await import_categories(repository=repository, data=data)

    assert first.created == 1
    assert second.created == 0
    assert second.updated == 1
    assert len(repository.categories) == 1


@pytest.mark.asyncio
async def test_one_c_import_categories_links_parent_from_same_batch() -> None:
    repository = FakeCategoryRepository()

    response = await import_categories(
        repository=repository,
        data=build_request(
            OneCCategoryImportItem(external_1c_id="cat-001", name="Фрукты", slug="frukty"),
            OneCCategoryImportItem(
                external_1c_id="cat-002",
                name="Яблоки",
                slug="yabloki",
                parent_external_1c_id="cat-001",
            ),
        ),
    )

    parent = next(category for category in repository.categories if category.external_1c_id == "cat-001")
    child = next(category for category in repository.categories if category.external_1c_id == "cat-002")
    assert response.created == 2
    assert child.parent_id == parent.id


@pytest.mark.asyncio
async def test_verify_one_c_token_invalid_returns_401(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "api_token", "secret")

    with pytest.raises(HTTPException) as exc_info:
        await verify_one_c_token(authorization="Bearer wrong")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_one_c_import_categories_empty_items_returns_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await import_one_c_categories.__dishka_orig_func__(
            body=OneCCategoryImportRequest(items=[]),
            _token=None,
            config=SimpleNamespace(one_c=SimpleNamespace(import_max_batch_size=1000)),
            commiter=FakeCommiter(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_one_c_import_categories_unknown_parent_partial_error() -> None:
    response = await import_categories(
        data=build_request(
            OneCCategoryImportItem(
                external_1c_id="cat-009",
                name="Неизвестный раздел",
                parent_external_1c_id="missing-parent",
            ),
        ),
    )

    assert response.created == 0
    assert response.skipped == 1
    assert response.errors[0].field == "parent_external_1c_id"
    assert response.errors[0].message == "Родительская категория не найдена"


@pytest.mark.asyncio
async def test_one_c_import_categories_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await import_categories(
        redis_service=redis_service,
        data=build_request(OneCCategoryImportItem(external_1c_id="cat-001", name="Фрукты")),
    )

    assert "categories:list:*" in redis_service.deleted_patterns
    assert "categories:tree:*" in redis_service.deleted_patterns
    assert "admin:categories:*" in redis_service.deleted_patterns
    assert "products:list:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_one_c_import_categories_creates_integration_log() -> None:
    integration_log_repository = FakeIntegrationLogRepository()

    await import_categories(
        integration_log_repository=integration_log_repository,
        data=build_request(OneCCategoryImportItem(external_1c_id="cat-001", name="Фрукты")),
    )

    log = integration_log_repository.logs[0]
    assert log["system"] == "1c"
    assert log["entity_type"] == "categories"
    assert log["status"] == "success"
    assert "api_token" not in log["request_payload"]


@pytest.mark.asyncio
async def test_one_c_import_products_creates_new_products() -> None:
    product_repository = FakeProductRepository()

    response = await import_products(
        product_repository=product_repository,
        data=build_product_request(build_product_item()),
    )

    assert response.created == 1
    assert response.updated == 0
    product = product_repository.products[0]
    assert product.external_1c_id == "prod-001"
    assert product.article == "APL-001"
    assert product.sync_status == "synced"
    assert product.last_sync_at is not None
    assert product.source == "1c"


@pytest.mark.asyncio
async def test_one_c_import_products_updates_existing_products() -> None:
    product = build_product(name="Старое", slug="staroe")
    product_repository = FakeProductRepository([product])

    response = await import_products(
        product_repository=product_repository,
        data=build_product_request(build_product_item(name="Новое", product_type="piece", quantity_step="1", min_quantity="1")),
    )

    assert response.created == 0
    assert response.updated == 1
    assert product.name == "Новое"
    assert product.article == "APL-001"
    assert product.product_type == "piece"


@pytest.mark.asyncio
async def test_one_c_import_products_repeated_import_does_not_create_duplicates() -> None:
    product_repository = FakeProductRepository()
    data = build_product_request(build_product_item())

    first = await import_products(product_repository=product_repository, data=data)
    second = await import_products(product_repository=product_repository, data=data)

    assert first.created == 1
    assert second.created == 0
    assert second.updated == 1
    assert len(product_repository.products) == 1


@pytest.mark.asyncio
async def test_one_c_import_products_generates_slug() -> None:
    product_repository = FakeProductRepository()

    await import_products(
        product_repository=product_repository,
        data=build_product_request(build_product_item(name="Яблоки красные")),
    )

    assert product_repository.products[0].slug == "yabloki-krasnye"


@pytest.mark.asyncio
async def test_one_c_import_products_adds_slug_suffix_when_taken() -> None:
    existing = build_product(product_id=1, external_1c_id="other", name="Яблоки красные", slug="yabloki-krasnye")
    product_repository = FakeProductRepository([existing])

    await import_products(
        product_repository=product_repository,
        data=build_product_request(build_product_item()),
    )

    created = next(product for product in product_repository.products if product.external_1c_id == "prod-001")
    assert created.slug == "yabloki-krasnye-prod-001"


@pytest.mark.asyncio
async def test_one_c_import_products_links_category_by_external_1c_id() -> None:
    category = build_category(category_id=10, external_1c_id="cat-001")
    product_repository = FakeProductRepository()

    await import_products(
        product_repository=product_repository,
        category_repository=FakeCategoryRepository([category]),
        data=build_product_request(build_product_item()),
    )

    assert product_repository.products[0].category_id == 10


@pytest.mark.asyncio
async def test_one_c_import_products_unknown_category_returns_partial_error() -> None:
    response = await import_products(
        category_repository=FakeCategoryRepository([]),
        data=build_product_request(build_product_item()),
    )

    assert response.created == 0
    assert response.skipped == 1
    assert response.errors[0].field == "category_external_1c_id"
    assert response.errors[0].message == "Категория из 1С не найдена"


@pytest.mark.asyncio
async def test_one_c_import_products_empty_items_returns_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await import_one_c_products.__dishka_orig_func__(
            body=OneCProductImportRequest(items=[]),
            _token=None,
            config=SimpleNamespace(one_c=SimpleNamespace(import_max_batch_size=1000)),
            commiter=FakeCommiter(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_one_c_import_products_does_not_overwrite_manual_fields() -> None:
    product = build_product(
        description="Описание сайта",
        meta_title="SEO title",
        meta_description="SEO description",
        slug="custom-slug",
    )

    await import_products(
        product_repository=FakeProductRepository([product]),
        data=build_product_request(build_product_item(name="Новое", product_type="piece", quantity_step="1", min_quantity="1")),
    )

    assert product.description == "Описание сайта"
    assert product.meta_title == "SEO title"
    assert product.meta_description == "SEO description"
    assert product.slug == "custom-slug"


@pytest.mark.asyncio
async def test_one_c_import_products_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await import_products(
        redis_service=redis_service,
        data=build_product_request(build_product_item()),
    )

    assert "products:list:*" in redis_service.deleted_patterns
    assert "products:detail:*" in redis_service.deleted_patterns
    assert "products:slug:*" in redis_service.deleted_patterns
    assert "products:search:*" in redis_service.deleted_patterns
    assert "products:popular:*" in redis_service.deleted_patterns
    assert "products:new:*" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns
    assert "categories:tree:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_one_c_import_products_creates_integration_log() -> None:
    integration_log_repository = FakeIntegrationLogRepository()

    await import_products(
        integration_log_repository=integration_log_repository,
        data=build_product_request(build_product_item()),
    )

    log = integration_log_repository.logs[0]
    assert log["system"] == "1c"
    assert log["entity_type"] == "products"
    assert log["status"] == "success"


@pytest.mark.asyncio
async def test_one_c_import_prices_updates_price() -> None:
    product = build_product(price="100.00")

    response = await import_prices(
        product_repository=FakeProductRepository([product]),
        data=build_price_request(build_price_item(price="150.00")),
    )

    assert response.updated == 1
    assert product.price == build_price_item(price="150.00").price
    assert product.currency == "RUB"
    assert product.price_updated_at is not None
    assert product.sync_status == "synced"
    assert product.last_sync_at is not None


@pytest.mark.asyncio
async def test_one_c_import_prices_updates_old_price() -> None:
    product = build_product(price="100.00", old_price=None)

    await import_prices(
        product_repository=FakeProductRepository([product]),
        data=build_price_request(build_price_item(price="150.00", old_price="180.00")),
    )

    assert product.old_price == build_price_item(old_price="180.00").old_price


@pytest.mark.asyncio
async def test_one_c_import_prices_negative_price_returns_error() -> None:
    response = await import_prices(
        data=build_price_request(build_price_item(price="-1.00")),
    )

    assert response.updated == 0
    assert response.skipped == 1
    assert response.errors[0].field == "price"
    assert response.errors[0].message == "Цена не может быть отрицательной"


@pytest.mark.asyncio
async def test_one_c_import_prices_unknown_product_returns_error() -> None:
    response = await import_prices(
        product_repository=FakeProductRepository([]),
        data=build_price_request(build_price_item(product_external_1c_id="prod-404")),
    )

    assert response.updated == 0
    assert response.skipped == 1
    assert response.errors[0].product_external_1c_id == "prod-404"
    assert response.errors[0].message == "Товар не найден"


@pytest.mark.asyncio
async def test_one_c_import_prices_invalid_currency_returns_error() -> None:
    response = await import_prices(
        data=build_price_request(build_price_item(currency="USD")),
    )

    assert response.updated == 0
    assert response.skipped == 1
    assert response.errors[0].field == "currency"
    assert response.errors[0].message == "Валюта не поддерживается"


@pytest.mark.asyncio
async def test_one_c_import_prices_creates_history_when_price_changed() -> None:
    history_repository = FakeProductPriceHistoryRepository()
    product = build_product(product_id=10, price="100.00")

    await import_prices(
        product_repository=FakeProductRepository([product]),
        history_repository=history_repository,
        data=build_price_request(build_price_item(price="150.00")),
    )

    history = history_repository.items[0]
    assert history["product_id"] == 10
    assert history["old_price"] == "100.00"
    assert history["new_price"] == build_price_item(price="150.00").price
    assert history["source"] == "1c"


@pytest.mark.asyncio
async def test_one_c_import_prices_does_not_create_history_without_price_change() -> None:
    history_repository = FakeProductPriceHistoryRepository()
    product = build_product(price=build_price_item(price="150.00").price)

    await import_prices(
        product_repository=FakeProductRepository([product]),
        history_repository=history_repository,
        data=build_price_request(build_price_item(price="150.00")),
    )

    assert history_repository.items == []


@pytest.mark.asyncio
async def test_one_c_import_prices_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await import_prices(
        redis_service=redis_service,
        data=build_price_request(build_price_item(price="150.00")),
    )

    assert "products:list:*" in redis_service.deleted_patterns
    assert "products:detail:*" in redis_service.deleted_patterns
    assert "products:slug:*" in redis_service.deleted_patterns
    assert "products:search:*" in redis_service.deleted_patterns
    assert "products:discounted:*" in redis_service.deleted_patterns
    assert "cart:*" in redis_service.deleted_patterns
    assert "cart:summary:*" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_one_c_import_prices_creates_integration_log() -> None:
    integration_log_repository = FakeIntegrationLogRepository()

    await import_prices(
        integration_log_repository=integration_log_repository,
        data=build_price_request(build_price_item(price="150.00")),
    )

    log = integration_log_repository.logs[0]
    assert log["system"] == "1c"
    assert log["entity_type"] == "product_prices"
    assert log["status"] == "success"


@pytest.mark.asyncio
async def test_one_c_import_stocks_updates_stock() -> None:
    product = build_product(stock_quantity="10.0")

    response = await import_stocks(
        product_repository=FakeProductRepository([product]),
        data=build_stock_request(build_stock_item(stock_quantity="30.5", reserved_quantity="2.0")),
    )

    assert response.updated == 1
    assert product.stock_quantity == build_stock_item(stock_quantity="30.5").stock_quantity
    assert product.reserved_quantity == build_stock_item(reserved_quantity="2.0").reserved_quantity
    assert product.stock_updated_at is not None
    assert product.last_sync_at is not None


@pytest.mark.asyncio
async def test_one_c_import_stocks_negative_stock_quantity_returns_error() -> None:
    response = await import_stocks(
        data=build_stock_request(build_stock_item(stock_quantity="-1")),
    )

    assert response.updated == 0
    assert response.skipped == 1
    assert response.errors[0].field == "stock_quantity"
    assert response.errors[0].message == "Остаток не может быть отрицательным"


@pytest.mark.asyncio
async def test_one_c_import_stocks_negative_reserved_quantity_returns_error() -> None:
    response = await import_stocks(
        data=build_stock_request(build_stock_item(reserved_quantity="-1")),
    )

    assert response.updated == 0
    assert response.skipped == 1
    assert response.errors[0].field == "reserved_quantity"
    assert response.errors[0].message == "Резерв не может быть отрицательным"


@pytest.mark.asyncio
async def test_one_c_import_stocks_unknown_product_returns_error() -> None:
    response = await import_stocks(
        product_repository=FakeProductRepository([]),
        data=build_stock_request(build_stock_item(product_external_1c_id="prod-404")),
    )

    assert response.updated == 0
    assert response.skipped == 1
    assert response.errors[0].product_external_1c_id == "prod-404"
    assert response.errors[0].message == "Товар не найден"


@pytest.mark.asyncio
async def test_one_c_import_stocks_updates_availability_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "auto_availability_from_stock", True)
    product = build_product(stock_quantity="10.0", is_available=True, is_active=True)

    await import_stocks(
        product_repository=FakeProductRepository([product]),
        data=build_stock_request(build_stock_item(stock_quantity="0")),
    )

    assert product.is_available is False

    await import_stocks(
        product_repository=FakeProductRepository([product]),
        data=build_stock_request(build_stock_item(stock_quantity="5")),
    )

    assert product.is_available is True


@pytest.mark.asyncio
async def test_one_c_import_stocks_creates_stock_movement() -> None:
    product = build_product(product_id=10, stock_quantity="10.0", low_stock_threshold="3")
    stock_movement_repository = FakeStockMovementRepository()

    await import_stocks(
        product_repository=FakeProductRepository([product]),
        stock_movement_repository=stock_movement_repository,
        data=build_stock_request(build_stock_item(stock_quantity="30.5", warehouse_external_1c_id="wh-001")),
    )

    movement = stock_movement_repository.items[0]
    assert movement["product_id"] == 10
    assert movement["old_quantity"] == "10.0"
    assert movement["new_quantity"] == build_stock_item(stock_quantity="30.5").stock_quantity
    assert movement["source"] == "1c"
    assert movement["warehouse_external_1c_id"] == "wh-001"


@pytest.mark.asyncio
async def test_one_c_import_stocks_does_not_create_movement_without_stock_change() -> None:
    stock_quantity = build_stock_item(stock_quantity="30.5").stock_quantity
    product = build_product(stock_quantity=stock_quantity)
    stock_movement_repository = FakeStockMovementRepository()

    await import_stocks(
        product_repository=FakeProductRepository([product]),
        stock_movement_repository=stock_movement_repository,
        data=build_stock_request(build_stock_item(stock_quantity="30.5")),
    )

    assert stock_movement_repository.items == []


@pytest.mark.asyncio
async def test_one_c_import_stocks_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await import_stocks(
        redis_service=redis_service,
        data=build_stock_request(build_stock_item(stock_quantity="30.5")),
    )

    assert "products:list:*" in redis_service.deleted_patterns
    assert "products:detail:*" in redis_service.deleted_patterns
    assert "products:slug:*" in redis_service.deleted_patterns
    assert "products:search:*" in redis_service.deleted_patterns
    assert "products:popular:*" in redis_service.deleted_patterns
    assert "products:discounted:*" in redis_service.deleted_patterns
    assert "cart:*" in redis_service.deleted_patterns
    assert "cart:summary:*" in redis_service.deleted_patterns
    assert "admin:dashboard:low_stock:*" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_one_c_import_stocks_creates_integration_log() -> None:
    integration_log_repository = FakeIntegrationLogRepository()

    await import_stocks(
        integration_log_repository=integration_log_repository,
        data=build_stock_request(build_stock_item(stock_quantity="30.5")),
    )

    log = integration_log_repository.logs[0]
    assert log["system"] == "1c"
    assert log["entity_type"] == "product_stocks"
    assert log["status"] == "success"


@pytest.mark.asyncio
async def test_one_c_import_images_imports_image_url_without_download(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "download_images", False)
    product_image_repository = FakeProductImageRepository()

    response = await import_images(
        product_image_repository=product_image_repository,
        data=build_image_request(build_image_item()),
    )

    assert response.created == 1
    image = product_image_repository.images[0]
    assert image.file_id is None
    assert image.external_url == "https://1c.example.com/images/apple.png"
    assert image.url == "https://1c.example.com/images/apple.png"
    assert image.is_main is True


@pytest.mark.asyncio
async def test_one_c_import_images_imports_image_url_with_download(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "download_images", True)
    product_image_repository = FakeProductImageRepository()
    upload_repository = FakeUploadRepository()
    storage_service = FakeStorageService()

    response = await import_images(
        product_image_repository=product_image_repository,
        upload_repository=upload_repository,
        storage_service=storage_service,
        image_download_service=FakeImageDownloadService(),
        data=build_image_request(build_image_item()),
    )

    assert response.created == 1
    assert product_image_repository.images[0].file_id == 1
    assert upload_repository.items[0]["mime_type"] == "image/png"
    assert storage_service.saved


@pytest.mark.asyncio
async def test_one_c_import_images_imports_base64(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "download_images", False)
    content_base64 = base64.b64encode(build_png_content()).decode("ascii")
    upload_repository = FakeUploadRepository()

    response = await import_images(
        upload_repository=upload_repository,
        data=build_image_request(
            build_image_item(
                image_url=None,
                filename="apple.png",
                content_base64=content_base64,
            ),
        ),
    )

    assert response.created == 1
    assert upload_repository.items[0]["original_filename"] == "apple.png"
    assert upload_repository.items[0]["uploaded_by"] is None


@pytest.mark.asyncio
async def test_one_c_import_images_unknown_product_returns_error() -> None:
    response = await import_images(
        product_repository=FakeProductRepository([]),
        data=build_image_request(build_image_item(product_external_1c_id="prod-404")),
    )

    assert response.created == 0
    assert response.skipped == 1
    assert response.errors[0].product_external_1c_id == "prod-404"
    assert response.errors[0].message == "Товар не найден"


@pytest.mark.asyncio
async def test_one_c_import_images_bad_base64_returns_error() -> None:
    response = await import_images(
        data=build_image_request(
            build_image_item(
                image_url=None,
                filename="apple.png",
                content_base64="bad-base64",
            ),
        ),
    )

    assert response.created == 0
    assert response.skipped == 1
    assert response.errors[0].message == "Некорректный base64"


@pytest.mark.asyncio
async def test_one_c_import_images_large_file_returns_error(monkeypatch) -> None:
    monkeypatch.setattr(settings.media, "max_image_size_mb", 0)
    content_base64 = base64.b64encode(build_png_content()).decode("ascii")

    response = await import_images(
        data=build_image_request(
            build_image_item(
                image_url=None,
                filename="apple.png",
                content_base64=content_base64,
            ),
        ),
    )

    assert response.created == 0
    assert response.skipped == 1
    assert response.errors[0].message == "Файл слишком большой"


@pytest.mark.asyncio
async def test_one_c_import_images_main_unsets_other_main(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "download_images", False)
    product_image_repository = FakeProductImageRepository(
        [build_product_image(image_id=1, product_id=1, image_external_1c_id="old", is_main=True)],
    )

    await import_images(
        product_image_repository=product_image_repository,
        data=build_image_request(build_image_item(image_external_1c_id="new", is_main=True)),
    )

    old_image = next(image for image in product_image_repository.images if image.image_external_1c_id == "old")
    new_image = next(image for image in product_image_repository.images if image.image_external_1c_id == "new")
    assert old_image.is_main is False
    assert new_image.is_main is True


@pytest.mark.asyncio
async def test_one_c_import_images_repeated_external_id_updates_without_duplicate(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "download_images", False)
    existing = build_product_image(image_id=1, product_id=1, image_external_1c_id="img-001", sort_order=1, is_main=False)
    product_image_repository = FakeProductImageRepository([existing])

    response = await import_images(
        product_image_repository=product_image_repository,
        data=build_image_request(build_image_item(sort_order=5, is_main=True)),
    )

    assert response.created == 0
    assert response.updated == 1
    assert len(product_image_repository.images) == 1
    assert existing.sort_order == 5
    assert existing.is_main is True


@pytest.mark.asyncio
async def test_one_c_import_images_invalidates_cache(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "download_images", False)
    redis_service = FakeRedisService()

    await import_images(
        redis_service=redis_service,
        data=build_image_request(build_image_item()),
    )

    assert "products:detail:1:*" in redis_service.deleted_patterns
    assert "products:slug:yabloki:*" in redis_service.deleted_patterns
    assert "products:list:*" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns
    assert "admin:products:detail:1" in redis_service.deleted


@pytest.mark.asyncio
async def test_one_c_import_images_creates_integration_log(monkeypatch) -> None:
    monkeypatch.setattr(settings.one_c, "download_images", False)
    integration_log_repository = FakeIntegrationLogRepository()

    await import_images(
        integration_log_repository=integration_log_repository,
        data=build_image_request(build_image_item()),
    )

    log = integration_log_repository.logs[0]
    assert log["system"] == "1c"
    assert log["entity_type"] == "product_images"
    assert log["status"] == "success"
