from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.integration import import_one_c_categories, import_one_c_products
from source.api.dependencies import verify_one_c_token
from source.config.settings import settings
from source.schemas.pydantic.one_c import (
    OneCCategoryImportItem,
    OneCCategoryImportRequest,
    OneCPriceImportItem,
    OneCPriceImportRequest,
    OneCProductImportItem,
    OneCProductImportRequest,
)
from source.services.admin_product_cache import AdminProductCacheService
from source.services.admin_category_cache import AdminCategoryCacheService
from source.services.cart_cache import CartCacheService
from source.services.category_cache import CategoryCacheService
from source.services.one_c import CategorySyncService, IntegrationLogService, OneCImportService, ProductPriceSyncService, ProductSyncService, SlugService
from source.services.product_cache import ProductCacheService


class FakeRedisService:
    def __init__(self) -> None:
        self.deleted_patterns: list[str] = []

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)


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


class FakeProductPriceHistoryRepository:
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
        is_active=is_active,
        is_available=is_available,
        sync_status=sync_status,
        last_sync_at=last_sync_at,
        source=source,
        description=description,
        meta_title=meta_title,
        meta_description=meta_description,
    )


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
