from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.category import CategoryNotFoundError
from source.errors.product import ProductNotFoundError, ProductSlugAlreadyExistsError
from source.schemas.pydantic.admin_product import (
    AdminProductCreateRequest,
    AdminProductCategoryResponse,
    AdminProductListItemResponse,
    AdminProductListQueryParams,
    AdminProductListResponse,
    AdminProductUpdateRequest,
    ProductAvailabilityUpdateRequest,
    ProductStockUpdateRequest,
)
from source.services.admin_auth import PermissionService
from source.services.admin_product import AdminProductService
from source.services.admin_product_cache import AdminProductCacheService
from source.services.stock import StockMovementService, StockService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.deleted_patterns = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)

    async def delete(self, key: str) -> None:
        self.deleted_patterns.append(key)


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class FakeProductRepository:
    def __init__(self, *, products: list[SimpleNamespace]) -> None:
        self.products = products
        self.called = False
        self.created_product = None

    async def admin_get_list(self, *, session, query: AdminProductListQueryParams):
        self.called = True
        products = self._filter(query=query)
        products = self._sort(products=products, sort=query.sort)
        return [self._build_response(product) for product in products[query.offset : query.offset + query.limit]]

    async def admin_count(self, *, session, query: AdminProductListQueryParams):
        return len(self._filter(query=query))

    async def admin_get_by_id(self, *, session, product_id: int):
        product = next(
            (item for item in self.products if item.id == product_id and not item.is_deleted),
            None,
        )
        if product is None:
            return None
        return product, product.category

    async def get_by_slug(self, *, session, slug: str):
        return next((product for product in self.products if product.slug == slug), None)

    async def get_by_sku(self, *, session, sku: str):
        return next((product for product in self.products if product.article == sku), None)

    async def get_by_barcode(self, *, session, barcode: str):
        return next((product for product in self.products if product.barcode == barcode), None)

    async def create(self, *, session, **data):
        product = SimpleNamespace(id=55, external_1c_id=None, **data)
        self.created_product = product
        self.products.append(product)
        return product

    async def update(self, *, session, product, data: dict):
        for field, value in data.items():
            setattr(product, field, value)
        product.updated_date = datetime(2026, 5, 12, 11)
        return product

    async def soft_delete(self, *, session, product, deleted_at: datetime, deleted_by: int):
        product.is_deleted = True
        product.is_active = False
        product.is_available = False
        product.deleted_at = deleted_at
        product.deleted_by = deleted_by
        return product

    async def update_availability(self, *, session, product, is_available: bool):
        product.is_available = is_available
        product.updated_date = datetime(2026, 5, 12, 11)
        return product

    async def update_stock(self, *, session, product, stock_quantity, low_stock_threshold, is_available: bool):
        product.stock_quantity = stock_quantity
        product.low_stock_threshold = low_stock_threshold
        product.is_available = is_available
        product.updated_date = datetime(2026, 5, 12, 11)
        return product

    def _filter(self, *, query: AdminProductListQueryParams):
        products = [product for product in self.products if not product.is_deleted]
        if query.q is not None:
            q = query.q.lower()
            products = [
                product
                for product in products
                if q in product.name.lower()
                or q in (product.article or "").lower()
                or q in (product.barcode or "").lower()
                or q in (product.external_1c_id or "").lower()
            ]
        if query.category_id is not None:
            products = [product for product in products if product.category.id == query.category_id]
        if query.is_active is not None:
            products = [product for product in products if product.is_active is query.is_active]
        if query.is_available is not None:
            products = [product for product in products if product.is_available is query.is_available]
        if query.in_stock is True:
            products = [product for product in products if product.stock_quantity > 0]
        elif query.in_stock is False:
            products = [product for product in products if product.stock_quantity <= 0]
        if query.low_stock is True:
            products = [product for product in products if product.stock_quantity <= product.low_stock_threshold]
        elif query.low_stock is False:
            products = [product for product in products if product.stock_quantity > product.low_stock_threshold]
        if query.product_type is not None:
            products = [product for product in products if product.product_type == query.product_type]
        if query.sync_status is not None:
            products = [product for product in products if product.sync_status == query.sync_status]
        return products

    def _sort(self, *, products: list[SimpleNamespace], sort: str):
        match sort:
            case "name_asc":
                return sorted(products, key=lambda product: (product.name, product.id))
            case "price_asc":
                return sorted(products, key=lambda product: (product.price, product.name))
            case "stock_asc":
                return sorted(products, key=lambda product: (product.stock_quantity, product.name))
            case "newest" | _:
                return sorted(products, key=lambda product: (product.created_date, product.id), reverse=True)

    def _build_response(self, product: SimpleNamespace) -> AdminProductListItemResponse:
        return AdminProductListItemResponse(
            id=product.id,
            name=product.name,
            slug=product.slug,
            sku=product.article,
            barcode=product.barcode,
            category=AdminProductCategoryResponse(id=product.category.id, name=product.category.name),
            price=product.price,
            unit=product.unit,
            product_type=product.product_type,
            stock_quantity=product.stock_quantity,
            low_stock_threshold=product.low_stock_threshold,
            is_active=product.is_active,
            is_available=product.is_available,
            sync_status=product.sync_status,
            external_1c_id=product.external_1c_id,
        )


def build_user(*, role=UserRole.ADMIN, is_active: bool = True, is_deleted: bool = False):
    return SimpleNamespace(
        id=1,
        role=role,
        is_active=is_active,
        is_deleted=is_deleted,
        email="admin@example.com",
        phone="+79990000000",
    )


def build_product(
    *,
    product_id: int,
    name: str,
    article: str | None = None,
    barcode: str | None = None,
    price: Decimal = Decimal("100.00"),
    stock_quantity: Decimal = Decimal("10"),
    min_quantity: Decimal = Decimal("5"),
    low_stock_threshold: Decimal = Decimal("5"),
    is_active: bool = True,
    is_available: bool = True,
    is_deleted: bool = False,
    product_type: str = "piece",
    sync_status: str | None = "synced",
    external_1c_id: str | None = None,
    created_date: datetime | None = None,
):
    return SimpleNamespace(
        id=product_id,
        name=name,
        slug=f"product-{product_id}",
        description="Описание товара",
        article=article or f"SKU-{product_id}",
        barcode=barcode,
        category_id=10,
        category=SimpleNamespace(id=10, name="Фрукты"),
        price=price,
        old_price=None,
        unit="kg" if product_type == "weight" else "pcs",
        product_type=product_type,
        quantity_step=Decimal("0.5") if product_type == "weight" else Decimal("1"),
        stock_quantity=stock_quantity,
        min_quantity=min_quantity,
        low_stock_threshold=low_stock_threshold,
        is_active=is_active,
        is_available=is_available,
        is_deleted=is_deleted,
        deleted_at=None,
        deleted_by=None,
        sync_status=sync_status,
        external_1c_id=external_1c_id,
        meta_title="SEO title",
        meta_description="SEO description",
        created_date=created_date or datetime(2026, 5, product_id),
        updated_date=datetime(2026, 5, product_id, 10),
    )


def build_repository() -> FakeProductRepository:
    return FakeProductRepository(
        products=[
            build_product(
                product_id=1,
                name="Яблоки красные",
                article="APL-001",
                barcode="4600000000001",
                product_type="weight",
                external_1c_id="1c-abc-123",
            ),
            build_product(
                product_id=2,
                name="Молоко",
                is_active=False,
                stock_quantity=Decimal("0"),
                sync_status="pending",
            ),
            build_product(
                product_id=3,
                name="Груши",
                stock_quantity=Decimal("2"),
                min_quantity=Decimal("5"),
                sync_status="error",
            ),
            build_product(product_id=4, name="Удаленный товар", is_deleted=True),
        ],
    )


class FakeCategoryRepository:
    def __init__(self, *, exists: bool = True) -> None:
        self.exists = exists

    async def get_by_id(self, *, session, category_id: int):
        if not self.exists:
            return None
        return SimpleNamespace(id=category_id, name="Фрукты")


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=1, **data)


class FakeProductAvailabilityLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=1, **data)


class FakeStockMovementRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=1, **data)


class FakeProductCacheService:
    async def invalidate_all(self, *, redis_service: FakeRedisService) -> None:
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:new:*")

    async def invalidate_product(self, *, redis_service: FakeRedisService, product_id: int, slug: str | None = None) -> None:
        await redis_service.delete_by_pattern(f"products:detail:{product_id}:*")
        if slug is not None:
            await redis_service.delete_by_pattern(f"products:slug:{slug}:*")
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:search:*")
        await redis_service.delete_by_pattern("products:popular:*")
        await redis_service.delete_by_pattern("products:discounted:*")
        await redis_service.delete_by_pattern("products:new:*")


class FakeCategoryCacheService:
    async def invalidate_all(self, *, redis_service: FakeRedisService) -> None:
        await redis_service.delete_by_pattern("categories:list:*")
        await redis_service.delete_by_pattern("categories:tree:*")


class FakeProductImageRepository:
    def __init__(self) -> None:
        self.called = False

    async def get_by_product_id(self, *, session, product_id: int):
        self.called = True
        return [
            SimpleNamespace(id=1, url="/media/apple.jpg", sort_order=0),
        ]


class FakeDiscountRepository:
    def __init__(self) -> None:
        self.called = False

    async def get_by_product_id(self, *, session, product_id: int):
        self.called = True
        return []


class FakeOrderItemRepository:
    def __init__(self, *, has_active_order: bool = False) -> None:
        self.has_active_order = has_active_order

    async def exists_active_order_by_product_id(self, *, session, product_id: int):
        return self.has_active_order


async def get_products(
    *,
    redis_service=None,
    user=None,
    product_repository=None,
    query=None,
):
    return await AdminProductService().get_products(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        query=query or AdminProductListQueryParams(),
        permission_service=PermissionService(),
        product_repository=product_repository or build_repository(),
        admin_product_cache_service=AdminProductCacheService(),
    )


def build_create_request(**overrides) -> AdminProductCreateRequest:
    data = {
        "name": "Яблоки красные",
        "slug": "yabloki-krasnye",
        "description": "Свежие красные яблоки",
        "category_id": 11,
        "price": Decimal("150.00"),
        "old_price": Decimal("180.00"),
        "unit": "kg",
        "product_type": "weight",
        "quantity_step": Decimal("0.5"),
        "min_quantity": Decimal("0.5"),
        "stock_quantity": Decimal("30.5"),
        "low_stock_threshold": Decimal("5"),
        "sku": "APL-NEW",
        "barcode": "4600000000002",
        "meta_title": "Яблоки красные купить онлайн",
        "meta_description": "Свежие яблоки с доставкой",
    }
    data.update(overrides)
    return AdminProductCreateRequest(**data)


async def create_product(
    *,
    redis_service=None,
    user=None,
    product_repository=None,
    category_repository=None,
    audit_log_repository=None,
    commiter=None,
    data=None,
):
    return await AdminProductService().create_product(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        data=data or build_create_request(),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        product_repository=product_repository or build_repository(),
        category_repository=category_repository or FakeCategoryRepository(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        product_cache_service=FakeProductCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
        category_cache_service=FakeCategoryCacheService(),
    )


async def get_product_detail(
    *,
    redis_service=None,
    user=None,
    product_repository=None,
    product_image_repository=None,
    discount_repository=None,
    product_id: int = 1,
):
    return await AdminProductService().get_product_detail(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        product_id=product_id,
        permission_service=PermissionService(),
        product_repository=product_repository or build_repository(),
        product_image_repository=product_image_repository or FakeProductImageRepository(),
        discount_repository=discount_repository or FakeDiscountRepository(),
        admin_product_cache_service=AdminProductCacheService(),
    )


async def update_product(
    *,
    redis_service=None,
    user=None,
    product_repository=None,
    category_repository=None,
    audit_log_repository=None,
    commiter=None,
    data=None,
    product_id: int = 1,
):
    return await AdminProductService().update_product(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        product_id=product_id,
        data=data or AdminProductUpdateRequest(name="Яблоки красные отборные", price=Decimal("160.00")),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        product_repository=product_repository or build_repository(),
        category_repository=category_repository or FakeCategoryRepository(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        product_cache_service=FakeProductCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
    )


async def delete_product(
    *,
    redis_service=None,
    user=None,
    product_repository=None,
    order_item_repository=None,
    audit_log_repository=None,
    commiter=None,
    product_id: int = 1,
):
    return await AdminProductService().delete_product(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        product_id=product_id,
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        product_repository=product_repository or build_repository(),
        order_item_repository=order_item_repository or FakeOrderItemRepository(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        product_cache_service=FakeProductCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
    )


async def update_availability(
    *,
    redis_service=None,
    user=None,
    product_repository=None,
    availability_log_repository=None,
    audit_log_repository=None,
    commiter=None,
    data=None,
    product_id: int = 1,
):
    return await AdminProductService().update_availability(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        product_id=product_id,
        data=data or ProductAvailabilityUpdateRequest(is_available=False, reason="Товар временно отсутствует"),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        product_repository=product_repository or build_repository(),
        product_availability_log_repository=availability_log_repository or FakeProductAvailabilityLogRepository(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        product_cache_service=FakeProductCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
    )


async def update_stock(
    *,
    redis_service=None,
    user=None,
    product_repository=None,
    stock_movement_repository=None,
    audit_log_repository=None,
    commiter=None,
    data=None,
    product_id: int = 1,
):
    return await AdminProductService().update_stock(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        product_id=product_id,
        data=data or ProductStockUpdateRequest(stock_quantity=Decimal("25"), low_stock_threshold=Decimal("5"), operation="set", reason="Ручная корректировка"),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        product_repository=product_repository or build_repository(),
        stock_service=StockService(),
        stock_movement_service=StockMovementService(),
        stock_movement_repository=stock_movement_repository or FakeStockMovementRepository(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        product_cache_service=FakeProductCacheService(),
        admin_product_cache_service=AdminProductCacheService(),
    )


@pytest.mark.asyncio
async def test_admin_products_list_success() -> None:
    response = await get_products()

    assert response.total == 3
    assert response.page == 1
    assert response.limit == 50
    assert response.items[0].id == 3
    assert response.items[0].sync_status == "error"
    assert response.items[0].external_1c_id is None


@pytest.mark.asyncio
async def test_admin_products_search_q() -> None:
    response = await get_products(query=AdminProductListQueryParams(q="  APL-001  "))

    assert response.total == 1
    assert response.items[0].name == "Яблоки красные"


@pytest.mark.asyncio
async def test_admin_products_filter_is_active() -> None:
    response = await get_products(query=AdminProductListQueryParams(is_active=False))

    assert response.total == 1
    assert response.items[0].name == "Молоко"


@pytest.mark.asyncio
async def test_admin_products_filter_low_stock() -> None:
    response = await get_products(query=AdminProductListQueryParams(low_stock=True, sort="stock_asc"))

    assert [item.id for item in response.items] == [2, 3]


@pytest.mark.asyncio
async def test_admin_products_filter_sync_status() -> None:
    response = await get_products(query=AdminProductListQueryParams(sync_status="pending"))

    assert response.total == 1
    assert response.items[0].id == 2


@pytest.mark.asyncio
async def test_admin_products_pagination() -> None:
    response = await get_products(query=AdminProductListQueryParams(page=2, limit=1, sort="name_asc"))

    assert response.total == 3
    assert response.pages == 3
    assert response.items[0].name == "Молоко"


@pytest.mark.asyncio
async def test_admin_products_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_products(user=build_user(role=UserRole.PICKER))


@pytest.mark.asyncio
async def test_admin_products_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    query = AdminProductListQueryParams(q="Яблоки")
    cached_response = AdminProductListResponse(
        items=[],
        total=0,
        page=1,
        limit=50,
        pages=0,
    )
    normalized_query = query.model_copy(update={"q": normalize_search_query(query.q)})
    query_hash = build_query_hash(normalized_query.model_dump())
    redis_service.values[f"admin:products:list:{query_hash}"] = cached_response.model_dump_json()
    product_repository = build_repository()

    response = await get_products(redis_service=redis_service, product_repository=product_repository, query=query)

    assert response == cached_response
    assert product_repository.called is False


@pytest.mark.asyncio
async def test_admin_products_response_is_cached() -> None:
    redis_service = FakeRedisService()
    query = AdminProductListQueryParams(sync_status="synced")

    await get_products(redis_service=redis_service, query=query)

    cache_key = f"admin:products:list:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.admin_list_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_product_create_success() -> None:
    product_repository = build_repository()
    commiter = FakeCommiter()

    response = await create_product(product_repository=product_repository, commiter=commiter)

    assert response.id == 55
    assert response.name == "Яблоки красные"
    assert response.category_id == 11
    assert response.product_type == "weight"
    assert product_repository.created_product.article == "APL-NEW"
    assert product_repository.created_product.sync_status == "manual"
    assert commiter.committed is True


@pytest.mark.asyncio
async def test_admin_product_create_slug_taken_error() -> None:
    product_repository = build_repository()

    with pytest.raises(ProductSlugAlreadyExistsError):
        await create_product(
            product_repository=product_repository,
            data=build_create_request(slug="product-1"),
        )


@pytest.mark.asyncio
async def test_admin_product_create_category_not_found_error() -> None:
    with pytest.raises(CategoryNotFoundError):
        await create_product(category_repository=FakeCategoryRepository(exists=False))


def test_admin_product_create_invalid_product_type_error() -> None:
    with pytest.raises(ValidationError):
        build_create_request(product_type="box")


def test_admin_product_create_invalid_quantity_step_error() -> None:
    with pytest.raises(ValidationError):
        build_create_request(product_type="weight", quantity_step=Decimal("0.3"))


@pytest.mark.asyncio
async def test_admin_product_create_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await create_product(redis_service=redis_service)

    assert "products:list:*" in redis_service.deleted_patterns
    assert "products:new:*" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns
    assert "categories:list:*" in redis_service.deleted_patterns
    assert "categories:tree:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_product_create_audit_log_created() -> None:
    audit_log_repository = FakeAuditLogRepository()

    await create_product(audit_log_repository=audit_log_repository)

    assert len(audit_log_repository.logs) == 1
    assert audit_log_repository.logs[0]["event"] == "admin_product_create"
    assert audit_log_repository.logs[0]["status"] == "success"
    assert audit_log_repository.logs[0]["details"]["product_id"] == 55


@pytest.mark.asyncio
async def test_admin_product_detail_success() -> None:
    image_repository = FakeProductImageRepository()
    discount_repository = FakeDiscountRepository()

    response = await get_product_detail(
        product_image_repository=image_repository,
        discount_repository=discount_repository,
    )

    assert response.id == 1
    assert response.name == "Яблоки красные"
    assert response.category_id == 10
    assert response.sku == "APL-001"
    assert response.barcode == "4600000000001"
    assert response.external_1c_id == "1c-abc-123"
    assert response.sync_status == "synced"
    assert response.images[0].url == "/media/apple.jpg"
    assert image_repository.called is True
    assert discount_repository.called is True


@pytest.mark.asyncio
async def test_admin_product_detail_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    cached_response = build_create_request().model_dump()
    response = await create_product(data=AdminProductCreateRequest(**cached_response))
    redis_service.values["admin:products:detail:1"] = response.model_dump_json()
    product_repository = build_repository()
    image_repository = FakeProductImageRepository()

    result = await get_product_detail(
        redis_service=redis_service,
        product_repository=product_repository,
        product_image_repository=image_repository,
    )

    assert result == response
    assert image_repository.called is False


@pytest.mark.asyncio
async def test_admin_product_detail_not_found_error() -> None:
    with pytest.raises(ProductNotFoundError):
        await get_product_detail(product_id=999)


@pytest.mark.asyncio
async def test_admin_product_detail_deleted_product_not_returned() -> None:
    with pytest.raises(ProductNotFoundError):
        await get_product_detail(product_id=4)


@pytest.mark.asyncio
async def test_admin_product_detail_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_product_detail(user=build_user(role=UserRole.PICKER))


@pytest.mark.asyncio
async def test_admin_product_update_success() -> None:
    product_repository = build_repository()
    commiter = FakeCommiter()

    response = await update_product(product_repository=product_repository, commiter=commiter)

    assert response.id == 1
    assert response.name == "Яблоки красные отборные"
    assert response.price == Decimal("160.00")
    assert response.updated_at == datetime(2026, 5, 12, 11)
    assert product_repository.products[0].name == "Яблоки красные отборные"
    assert commiter.committed is True


@pytest.mark.asyncio
async def test_admin_product_update_slug_taken_error() -> None:
    with pytest.raises(ProductSlugAlreadyExistsError):
        await update_product(data=AdminProductUpdateRequest(slug="product-2"))


@pytest.mark.asyncio
async def test_admin_product_update_category_not_found_error() -> None:
    with pytest.raises(CategoryNotFoundError):
        await update_product(
            data=AdminProductUpdateRequest(category_id=99),
            category_repository=FakeCategoryRepository(exists=False),
        )


@pytest.mark.asyncio
async def test_admin_product_update_empty_body_error() -> None:
    with pytest.raises(ValueError):
        await update_product(data=AdminProductUpdateRequest())


def test_admin_product_update_system_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        AdminProductUpdateRequest.model_validate({"external_1c_id": "1c-new"})


@pytest.mark.asyncio
async def test_admin_product_update_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await update_product(
        redis_service=redis_service,
        data=AdminProductUpdateRequest(slug="yabloki-krasnye-otbornye"),
    )

    assert "admin:products:detail:1" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns
    assert "products:detail:1:*" in redis_service.deleted_patterns
    assert "products:slug:product-1:*" in redis_service.deleted_patterns
    assert "products:slug:yabloki-krasnye-otbornye:*" in redis_service.deleted_patterns
    assert "products:list:*" in redis_service.deleted_patterns
    assert "products:search:*" in redis_service.deleted_patterns
    assert "products:discounted:*" in redis_service.deleted_patterns
    assert "products:new:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_product_update_audit_log_created() -> None:
    audit_log_repository = FakeAuditLogRepository()

    await update_product(
        audit_log_repository=audit_log_repository,
        data=AdminProductUpdateRequest(name="Яблоки красные отборные"),
    )

    assert len(audit_log_repository.logs) == 1
    assert audit_log_repository.logs[0]["event"] == "admin_product_update"
    assert audit_log_repository.logs[0]["status"] == "success"
    assert audit_log_repository.logs[0]["details"]["product_id"] == 1
    assert audit_log_repository.logs[0]["details"]["changes"]["name"]["old"] == "Яблоки красные"
    assert audit_log_repository.logs[0]["details"]["changes"]["name"]["new"] == "Яблоки красные отборные"


@pytest.mark.asyncio
async def test_admin_product_delete_success() -> None:
    product_repository = build_repository()
    commiter = FakeCommiter()

    response = await delete_product(product_repository=product_repository, commiter=commiter)

    assert response.message == "Товар удалён"
    assert product_repository.products[0].is_deleted is True
    assert product_repository.products[0].is_active is False
    assert product_repository.products[0].is_available is False
    assert product_repository.products[0].deleted_by == 1
    assert product_repository.products[0].deleted_at is not None
    assert commiter.committed is True


@pytest.mark.asyncio
async def test_admin_product_delete_not_found_error() -> None:
    with pytest.raises(ProductNotFoundError):
        await delete_product(product_id=999)


@pytest.mark.asyncio
async def test_admin_product_delete_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await delete_product(user=build_user(role=UserRole.PICKER))


@pytest.mark.asyncio
async def test_admin_product_delete_public_cache_invalidated() -> None:
    redis_service = FakeRedisService()

    await delete_product(redis_service=redis_service)

    assert "products:detail:1:*" in redis_service.deleted_patterns
    assert "products:slug:product-1:*" in redis_service.deleted_patterns
    assert "products:list:*" in redis_service.deleted_patterns
    assert "products:search:*" in redis_service.deleted_patterns
    assert "products:discounted:*" in redis_service.deleted_patterns
    assert "products:new:*" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns
    assert "admin:products:detail:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_product_delete_audit_log_created() -> None:
    audit_log_repository = FakeAuditLogRepository()

    await delete_product(audit_log_repository=audit_log_repository)

    assert len(audit_log_repository.logs) == 1
    assert audit_log_repository.logs[0]["event"] == "admin_product_delete"
    assert audit_log_repository.logs[0]["status"] == "success"
    assert audit_log_repository.logs[0]["details"]["product_id"] == 1


@pytest.mark.asyncio
async def test_admin_product_availability_disabled() -> None:
    product_repository = build_repository()
    old_stock_quantity = product_repository.products[0].stock_quantity

    response = await update_availability(product_repository=product_repository)

    assert response.id == 1
    assert response.is_available is False
    assert response.reason == "Товар временно отсутствует"
    assert product_repository.products[0].is_available is False
    assert product_repository.products[0].stock_quantity == old_stock_quantity


@pytest.mark.asyncio
async def test_admin_product_availability_enabled() -> None:
    product_repository = build_repository()
    product_repository.products[0].is_available = False

    response = await update_availability(
        product_repository=product_repository,
        data=ProductAvailabilityUpdateRequest(is_available=True, reason="Поступил на склад"),
    )

    assert response.is_available is True
    assert response.reason == "Поступил на склад"
    assert product_repository.products[0].is_available is True


@pytest.mark.asyncio
async def test_admin_product_availability_not_found_error() -> None:
    with pytest.raises(ProductNotFoundError):
        await update_availability(product_id=999)


@pytest.mark.asyncio
async def test_admin_product_availability_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await update_availability(user=build_user(role=UserRole.PICKER))


@pytest.mark.asyncio
async def test_admin_product_availability_cache_invalidated() -> None:
    redis_service = FakeRedisService()

    await update_availability(redis_service=redis_service)

    assert "products:detail:1:*" in redis_service.deleted_patterns
    assert "products:slug:product-1:*" in redis_service.deleted_patterns
    assert "products:list:*" in redis_service.deleted_patterns
    assert "products:search:*" in redis_service.deleted_patterns
    assert "admin:products:detail:1" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns
    assert "cart:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_product_availability_log_created() -> None:
    availability_log_repository = FakeProductAvailabilityLogRepository()
    audit_log_repository = FakeAuditLogRepository()

    await update_availability(
        availability_log_repository=availability_log_repository,
        audit_log_repository=audit_log_repository,
    )

    assert len(availability_log_repository.logs) == 1
    assert availability_log_repository.logs[0]["product_id"] == 1
    assert availability_log_repository.logs[0]["is_available"] is False
    assert availability_log_repository.logs[0]["reason"] == "Товар временно отсутствует"
    assert audit_log_repository.logs[0]["event"] == "admin_product_availability_update"


@pytest.mark.asyncio
async def test_admin_product_stock_set() -> None:
    product_repository = build_repository()

    response = await update_stock(
        product_repository=product_repository,
        data=ProductStockUpdateRequest(stock_quantity=Decimal("25"), low_stock_threshold=Decimal("5"), operation="set"),
    )

    assert response.stock_quantity == Decimal("25")
    assert response.low_stock_threshold == Decimal("5")
    assert response.is_available is True
    assert response.stock_display == "В наличии"
    assert product_repository.products[0].stock_quantity == Decimal("25")


@pytest.mark.asyncio
async def test_admin_product_stock_increase() -> None:
    response = await update_stock(
        data=ProductStockUpdateRequest(stock_quantity=Decimal("5"), operation="increase"),
    )

    assert response.stock_quantity == Decimal("15")


@pytest.mark.asyncio
async def test_admin_product_stock_decrease() -> None:
    response = await update_stock(
        data=ProductStockUpdateRequest(stock_quantity=Decimal("4"), operation="decrease"),
    )

    assert response.stock_quantity == Decimal("6")


@pytest.mark.asyncio
async def test_admin_product_stock_negative_error() -> None:
    with pytest.raises(ValueError):
        await update_stock(data=ProductStockUpdateRequest(stock_quantity=Decimal("11"), operation="decrease"))


@pytest.mark.asyncio
async def test_admin_product_stock_piece_fractional_error() -> None:
    with pytest.raises(ValueError):
        await update_stock(product_id=2, data=ProductStockUpdateRequest(stock_quantity=Decimal("25.5"), operation="set"))


@pytest.mark.asyncio
async def test_admin_product_stock_log_created() -> None:
    stock_movement_repository = FakeStockMovementRepository()

    await update_stock(
        stock_movement_repository=stock_movement_repository,
        data=ProductStockUpdateRequest(stock_quantity=Decimal("5"), operation="increase", reason="Ручная корректировка"),
    )

    assert len(stock_movement_repository.logs) == 1
    assert stock_movement_repository.logs[0]["product_id"] == 1
    assert stock_movement_repository.logs[0]["operation"] == "increase"
    assert stock_movement_repository.logs[0]["quantity"] == Decimal("5")
    assert stock_movement_repository.logs[0]["previous_stock_quantity"] == Decimal("10")
    assert stock_movement_repository.logs[0]["new_stock_quantity"] == Decimal("15")
    assert stock_movement_repository.logs[0]["reason"] == "Ручная корректировка"


@pytest.mark.asyncio
async def test_admin_product_stock_cache_invalidated() -> None:
    redis_service = FakeRedisService()

    await update_stock(redis_service=redis_service)

    assert "products:detail:1:*" in redis_service.deleted_patterns
    assert "products:slug:product-1:*" in redis_service.deleted_patterns
    assert "products:list:*" in redis_service.deleted_patterns
    assert "products:search:*" in redis_service.deleted_patterns
    assert "products:popular:*" in redis_service.deleted_patterns
    assert "products:discounted:*" in redis_service.deleted_patterns
    assert "admin:products:detail:1" in redis_service.deleted_patterns
    assert "admin:products:list:*" in redis_service.deleted_patterns
    assert "admin:dashboard:low_stock:*" in redis_service.deleted_patterns
    assert "cart:*" in redis_service.deleted_patterns
