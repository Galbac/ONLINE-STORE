from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.schemas.pydantic.admin_product import (
    AdminProductCategoryResponse,
    AdminProductListItemResponse,
    AdminProductListQueryParams,
    AdminProductListResponse,
)
from source.services.admin_auth import PermissionService
from source.services.admin_product import AdminProductService
from source.services.admin_product_cache import AdminProductCacheService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds


class FakeProductRepository:
    def __init__(self, *, products: list[SimpleNamespace]) -> None:
        self.products = products
        self.called = False

    async def admin_get_list(self, *, session, query: AdminProductListQueryParams):
        self.called = True
        products = self._filter(query=query)
        products = self._sort(products=products, sort=query.sort)
        return [self._build_response(product) for product in products[query.offset : query.offset + query.limit]]

    async def admin_count(self, *, session, query: AdminProductListQueryParams):
        return len(self._filter(query=query))

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
            products = [product for product in products if product.stock_quantity <= product.min_quantity]
        elif query.low_stock is False:
            products = [product for product in products if product.stock_quantity > product.min_quantity]
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
            low_stock_threshold=product.min_quantity,
            is_active=product.is_active,
            is_available=product.is_available,
            sync_status=product.sync_status,
            external_1c_id=product.external_1c_id,
        )


def build_user(*, role=UserRole.ADMIN, is_active: bool = True, is_deleted: bool = False):
    return SimpleNamespace(id=1, role=role, is_active=is_active, is_deleted=is_deleted)


def build_product(
    *,
    product_id: int,
    name: str,
    article: str | None = None,
    barcode: str | None = None,
    price: Decimal = Decimal("100.00"),
    stock_quantity: Decimal = Decimal("10"),
    min_quantity: Decimal = Decimal("5"),
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
        article=article or f"SKU-{product_id}",
        barcode=barcode,
        category=SimpleNamespace(id=10, name="Фрукты"),
        price=price,
        unit="kg" if product_type == "weight" else "pcs",
        product_type=product_type,
        stock_quantity=stock_quantity,
        min_quantity=min_quantity,
        is_active=is_active,
        is_available=is_available,
        is_deleted=is_deleted,
        sync_status=sync_status,
        external_1c_id=external_1c_id,
        created_date=created_date or datetime(2026, 5, product_id),
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
