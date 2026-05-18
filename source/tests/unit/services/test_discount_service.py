from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.schemas.pydantic.discount import ActiveDiscountsQueryParams, ActiveDiscountsResponse, DiscountProductsQueryParams, DiscountProductsResponse, DiscountShortResponse
from source.schemas.pydantic.product import ProductShortResponse
from source.services.discount import DiscountService
from source.services.discount_cache import DiscountCacheService
from source.utils.query_hash import build_query_hash


class FakeRedisService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.deleted_patterns = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)


class FakeDiscountRepository:
    def __init__(self, discounts=None) -> None:
        now = datetime.now(settings.tz)
        self.discounts = discounts if discounts is not None else [
            build_discount(discount_id=1, name="Скидка на яблоки", starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1)),
            build_discount(discount_id=2, name="Просроченная", starts_at=now - timedelta(days=3), ends_at=now - timedelta(days=1)),
            build_discount(discount_id=3, name="Будущая", starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=3)),
            build_discount(discount_id=4, name="Отключённая", is_active=False, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1)),
        ]
        self.get_active_calls = 0

    async def get_active(self, *, session, query, now):
        self.get_active_calls += 1
        items = self._active(query=query, now=now)
        return [DiscountShortResponse.model_validate(item, from_attributes=True) for item in items[query.offset : query.offset + query.limit]]

    async def count_active(self, *, session, query, now):
        return len(self._active(query=query, now=now))

    def _active(self, *, query, now):
        items = [
            discount for discount in self.discounts
            if discount.is_active and not discount.is_deleted
            and (discount.starts_at is None or discount.starts_at <= now)
            and (discount.ends_at is None or discount.ends_at >= now)
        ]
        if query.type is not None:
            items = [discount for discount in items if discount.type == query.type]
        return items


class FakeProductRepository:
    def __init__(self, products=None) -> None:
        self.products = products if products is not None else [build_product(product_id=1, name="Яблоки"), build_product(product_id=2, name="Без скидки", old_price=None)]
        self.get_calls = 0

    async def get_discounted_products(self, *, session, query):
        self.get_calls += 1
        products = [product for product in self.products if product.old_price is not None and product.old_price > product.price]
        if query.in_stock:
            products = [product for product in products if product.is_available]
        if query.category_id is not None:
            products = [product for product in products if product.category_id == query.category_id]
        if query.sort == "discount_desc":
            products.sort(key=lambda product: (product.old_price - product.price) / product.old_price, reverse=True)
        return [ProductShortResponse.model_validate(product, from_attributes=True) for product in products[query.offset : query.offset + query.limit]]

    async def count_discounted_products(self, *, session, query):
        return len(await self.get_discounted_products(session=session, query=query))


def build_discount(*, discount_id: int, name: str, type: str = "product", is_active: bool = True, starts_at=None, ends_at=None):
    return SimpleNamespace(
        id=discount_id,
        name=name,
        type=type,
        discount_type="percent",
        discount_value=Decimal("20"),
        starts_at=starts_at,
        ends_at=ends_at,
        is_active=is_active,
        is_deleted=False,
    )


def build_product(*, product_id: int, name: str, old_price=Decimal("180.00"), category_id: int = 1, is_available: bool = True):
    return SimpleNamespace(
        id=product_id,
        name=name,
        slug=f"product-{product_id}",
        preview_image_url=None,
        price=Decimal("150.00"),
        old_price=old_price,
        discount_percent=17 if old_price else None,
        unit="kg",
        product_type="weight",
        is_available=is_available,
        stock_display="В наличии",
        category_id=category_id,
    )


@pytest.mark.asyncio
async def test_get_active_discounts_success_filters_inactive_dates() -> None:
    response = await DiscountService().get_active_discounts(
        session=object(),
        redis_service=FakeRedisService(),
        discount_cache_service=DiscountCacheService(),
        discount_repository=FakeDiscountRepository(),
        query=ActiveDiscountsQueryParams(),
    )

    assert response.total == 1
    assert response.items[0].name == "Скидка на яблоки"


@pytest.mark.asyncio
async def test_get_active_discounts_type_filter_and_pagination() -> None:
    now = datetime.now(settings.tz)
    repository = FakeDiscountRepository([
        build_discount(discount_id=1, name="Товар", type="product", starts_at=now - timedelta(days=1)),
        build_discount(discount_id=2, name="Категория", type="category", starts_at=now - timedelta(days=1)),
    ])

    response = await DiscountService().get_active_discounts(
        session=object(),
        redis_service=FakeRedisService(),
        discount_cache_service=DiscountCacheService(),
        discount_repository=repository,
        query=ActiveDiscountsQueryParams(type="category", limit=1, offset=0),
    )

    assert response.total == 1
    assert response.items[0].type == "category"


@pytest.mark.asyncio
async def test_get_active_discounts_from_cache() -> None:
    redis_service = FakeRedisService()
    query = ActiveDiscountsQueryParams()
    cached = ActiveDiscountsResponse(items=[], total=0, limit=20, offset=0)
    redis_service.values[f"discounts:active:{build_query_hash(query.model_dump())}"] = cached.model_dump_json()
    repository = FakeDiscountRepository()

    response = await DiscountService().get_active_discounts(
        session=object(),
        redis_service=redis_service,
        discount_cache_service=DiscountCacheService(),
        discount_repository=repository,
        query=query,
    )

    assert response == cached
    assert repository.get_active_calls == 0


@pytest.mark.asyncio
async def test_get_discounted_products_filters_sort_pagination_and_cache() -> None:
    redis_service = FakeRedisService()
    query = DiscountProductsQueryParams(page=1, limit=1, category_id=1, in_stock=True, sort="discount_desc")
    response = await DiscountService().get_discounted_products(
        session=object(),
        redis_service=redis_service,
        discount_cache_service=DiscountCacheService(),
        product_repository=FakeProductRepository(),
        query=query,
    )

    assert response.total == 1
    assert response.items[0].name == "Яблоки"
    assert redis_service.ttls[f"discounts:products:{build_query_hash(query.model_dump())}"] == settings.discounts.products_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_discounted_products_from_cache() -> None:
    redis_service = FakeRedisService()
    query = DiscountProductsQueryParams()
    cached = DiscountProductsResponse.build(items=[], total=0, page=1, limit=24)
    redis_service.values[f"discounts:products:{build_query_hash(query.model_dump())}"] = cached.model_dump_json()
    repository = FakeProductRepository()

    response = await DiscountService().get_discounted_products(
        session=object(),
        redis_service=redis_service,
        discount_cache_service=DiscountCacheService(),
        product_repository=repository,
        query=query,
    )

    assert response == cached
    assert repository.get_calls == 0
