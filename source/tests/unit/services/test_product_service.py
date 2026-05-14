from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.errors.product import ProductNotFoundError
from source.schemas.pydantic.category import CategoryDetailResponse, CategoryShortResponse
from source.schemas.pydantic.product import (
    ProductBreadcrumbResponse,
    ProductCategoryShortResponse,
    ProductDetailQueryParams,
    ProductDetailResponse,
    ProductDiscountedQueryParams,
    ProductDiscountedResponse,
    ProductImageResponse,
    ProductListQueryParams,
    ProductListResponse,
    ProductNewQueryParams,
    ProductNewResponse,
    ProductPopularQueryParams,
    ProductPopularResponse,
    ProductSearchQueryParams,
    ProductSearchResponse,
    ProductSeoResponse,
    ProductSimilarQueryParams,
    ProductSimilarResponse,
    ProductShortResponse,
)
from source.services.product import ProductService
from source.services.product_cache import ProductCacheService
from source.utils.product import build_detailed_stock_display, build_stock_display, calculate_discount_percent
from source.utils.query_hash import build_query_hash
from source.utils.slug import normalize_slug, validate_slug


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted_patterns: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)


class FakeCategoryRepository:
    def __init__(self, categories: list[CategoryShortResponse] | None = None) -> None:
        self.categories = categories if categories is not None else [
            build_category(category_id=1, name="Фрукты", slug="frukty"),
            build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
        ]
        self.requested_slug: str | None = None

    async def get_parent_chain(self, *, session, category_id: int):
        categories_by_id = {category.id: category for category in self.categories}
        breadcrumbs = []
        current_category = categories_by_id.get(category_id)
        while current_category is not None:
            breadcrumbs.append(
                ProductBreadcrumbResponse(
                    id=current_category.id,
                    name=current_category.name,
                    slug=current_category.slug,
                ),
            )
            current_category = categories_by_id.get(current_category.parent_id)
        return list(reversed(breadcrumbs))

    async def get_active_by_id(self, *, session, category_id: int):
        for category in self.categories:
            if category.id == category_id:
                return CategoryDetailResponse(
                    id=category.id,
                    name=category.name,
                    slug=category.slug,
                    parent_id=category.parent_id,
                    image_url=category.image_url,
                    sort_order=category.sort_order,
                )
        return None

    async def get_active_by_slug(self, *, session, slug: str):
        self.requested_slug = slug
        for category in self.categories:
            if category.slug == slug:
                return CategoryDetailResponse(
                    id=category.id,
                    name=category.name,
                    slug=category.slug,
                    parent_id=category.parent_id,
                    image_url=category.image_url,
                    sort_order=category.sort_order,
                )
        return None

    async def get_active_all(self, *, session):
        return self.categories


class FakeProductRepository:
    def __init__(self, products: list[object] | None = None) -> None:
        self.products = products if products is not None else [
            build_product(product_id=55, name="Яблоки красные", slug="yabloki-krasnye", category_id=11),
            build_product(product_id=56, name="Бананы", slug="banany", category_id=1, price=Decimal("90.00")),
        ]
        self.query: ProductListQueryParams | None = None
        self.category_ids: set[int] | None = None
        self.requested_slug: str | None = None

    async def get_active_by_id(self, *, session, product_id: int):
        for product in self.products:
            if product.id == product_id and product.is_active and not product.is_deleted:
                return build_product_detail_response(product)
        return None

    async def get_active_by_slug(self, *, session, slug: str):
        self.requested_slug = slug
        for product in self.products:
            if product.slug == slug and product.is_active and not product.is_deleted:
                return build_product_detail_response(product)
        return None

    async def get_similar_active(self, *, session, product_id: int, category_id: int | None, limit: int = 4):
        products = [
            product
            for product in self.products
            if product.id != product_id
            and product.is_active
            and not product.is_deleted
            and (category_id is None or product.category_id == category_id)
        ]
        products = sorted(products, key=lambda product: (-product.popularity, product.name))
        return [build_product_response(product) for product in products[:limit]]

    async def get_similar_by_category(
        self,
        *,
        session,
        product_id: int,
        category_id: int | None,
        query: ProductSimilarQueryParams,
    ):
        products = [
            product
            for product in self.products
            if product.id != product_id
            and product.is_active
            and not product.is_deleted
            and (category_id is None or product.category_id == category_id)
        ]
        if query.in_stock:
            products = [product for product in products if product.is_available and product.stock_quantity > 0]
        products = sorted(products, key=lambda product: (-product.popularity, product.created_at, product.name))
        return [build_product_response(product) for product in products[: query.limit]]

    async def get_active_list(self, *, session, query: ProductListQueryParams, category_ids: set[int] | None = None):
        self.query = query
        self.category_ids = category_ids
        products = self._filter_products(query=query, category_ids=category_ids)
        products = self._sort_products(products=products, sort=query.sort)
        return [
            build_product_response(product)
            for product in products[query.offset : query.offset + query.limit]
        ]

    async def count_active(self, *, session, query: ProductListQueryParams, category_ids: set[int] | None = None):
        return len(self._filter_products(query=query, category_ids=category_ids))

    async def search_active(
        self,
        *,
        session,
        query: ProductSearchQueryParams,
        category_ids: set[int] | None = None,
    ):
        products = self._filter_search_products(query=query, category_ids=category_ids)
        products = self._sort_search_products(products=products, query=query)
        return [
            build_product_response(product)
            for product in products[query.offset : query.offset + query.limit]
        ]

    async def count_search_active(
        self,
        *,
        session,
        query: ProductSearchQueryParams,
        category_ids: set[int] | None = None,
    ):
        return len(self._filter_search_products(query=query, category_ids=category_ids))

    async def get_popular_active(
        self,
        *,
        session,
        query: ProductPopularQueryParams,
        category_ids: set[int] | None = None,
    ):
        products = [
            product
            for product in self.products
            if product.is_active and not product.is_deleted
        ]
        if category_ids is not None:
            products = [product for product in products if product.category_id in category_ids]
        if query.in_stock:
            products = [product for product in products if product.is_available and product.stock_quantity > 0]
        products = sorted(products, key=lambda product: (-product.popularity, product.name))
        return [build_product_response(product) for product in products[: query.limit]]

    async def get_discounted_active(
        self,
        *,
        session,
        query: ProductDiscountedQueryParams,
        category_ids: set[int] | None = None,
    ):
        products = self._filter_discounted_products(query=query, category_ids=category_ids)
        products = self._sort_discounted_products(products=products, query=query)
        return [
            build_product_response(product)
            for product in products[query.offset : query.offset + query.limit]
        ]

    async def count_discounted_active(
        self,
        *,
        session,
        query: ProductDiscountedQueryParams,
        category_ids: set[int] | None = None,
    ):
        return len(self._filter_discounted_products(query=query, category_ids=category_ids))

    async def get_new_active(
        self,
        *,
        session,
        query: ProductNewQueryParams,
        created_from: datetime,
        category_ids: set[int] | None = None,
    ):
        products = [
            product
            for product in self.products
            if product.is_active
            and not product.is_deleted
            and product.created_at >= created_from
        ]
        if category_ids is not None:
            products = [product for product in products if product.category_id in category_ids]
        if query.in_stock:
            products = [product for product in products if product.is_available and product.stock_quantity > 0]
        products = sorted(products, key=lambda product: (product.created_at, product.name), reverse=True)
        return [build_product_response(product) for product in products[: query.limit]]

    def _filter_products(self, *, query: ProductListQueryParams, category_ids: set[int] | None) -> list[object]:
        products = [
            product
            for product in self.products
            if product.is_active and not product.is_deleted
        ]
        if category_ids is not None:
            products = [product for product in products if product.category_id in category_ids]
        if query.in_stock is True:
            products = [product for product in products if product.is_available and product.stock_quantity > 0]
        if query.has_discount is True:
            products = [
                product
                for product in products
                if product.old_price is not None and product.old_price > product.price
            ]
        if query.product_type is not None:
            products = [product for product in products if product.product_type == query.product_type]
        if query.min_price is not None:
            products = [product for product in products if product.price >= query.min_price]
        if query.max_price is not None:
            products = [product for product in products if product.price <= query.max_price]
        return products

    def _sort_products(self, *, products: list[object], sort: str | None) -> list[object]:
        match sort:
            case "price_asc":
                return sorted(products, key=lambda product: (product.price, product.name))
            case "price_desc":
                return sorted(products, key=lambda product: (-product.price, product.name))
            case "newest":
                return sorted(products, key=lambda product: (product.created_at, product.name), reverse=True)
            case "popular":
                return sorted(products, key=lambda product: (-product.popularity, product.name))
            case "name_desc":
                return sorted(products, key=lambda product: product.name, reverse=True)
            case "name_asc" | _:
                return sorted(products, key=lambda product: product.name)

    def _filter_search_products(
        self,
        *,
        query: ProductSearchQueryParams,
        category_ids: set[int] | None,
    ) -> list[object]:
        search_query = query.q.lower()
        products = [
            product
            for product in self.products
            if product.is_active
            and not product.is_deleted
            and any(
                search_query in str(value).lower()
                for value in (
                    product.name,
                    product.description,
                    product.article,
                    product.barcode,
                    product.search_keywords,
                )
                if value is not None
            )
        ]
        if category_ids is not None:
            products = [product for product in products if product.category_id in category_ids]
        if query.in_stock is True:
            products = [product for product in products if product.is_available and product.stock_quantity > 0]
        if query.has_discount is True:
            products = [
                product
                for product in products
                if product.old_price is not None and product.old_price > product.price
            ]
        return products

    def _sort_search_products(
        self,
        *,
        products: list[object],
        query: ProductSearchQueryParams,
    ) -> list[object]:
        match query.sort:
            case "price_asc":
                return sorted(products, key=lambda product: (product.price, product.name))
            case "price_desc":
                return sorted(products, key=lambda product: (-product.price, product.name))
            case "newest":
                return sorted(products, key=lambda product: (product.created_at, product.name), reverse=True)
            case "popular":
                return sorted(products, key=lambda product: (-product.popularity, product.name))
            case "relevance" | _:
                search_query = query.q.lower()

                def relevance(product) -> tuple[int, int, str]:
                    if search_query in product.name.lower():
                        rank = 0
                    elif product.search_keywords is not None and search_query in product.search_keywords.lower():
                        rank = 1
                    elif product.description is not None and search_query in product.description.lower():
                        rank = 2
                    else:
                        rank = 3
                    return rank, -product.popularity, product.name

                return sorted(products, key=relevance)

    def _filter_discounted_products(
        self,
        *,
        query: ProductDiscountedQueryParams,
        category_ids: set[int] | None,
    ) -> list[object]:
        products = [
            product
            for product in self.products
            if product.is_active
            and not product.is_deleted
            and product.old_price is not None
            and product.old_price > product.price
        ]
        if category_ids is not None:
            products = [product for product in products if product.category_id in category_ids]
        if query.in_stock:
            products = [product for product in products if product.is_available and product.stock_quantity > 0]
        return products

    def _sort_discounted_products(
        self,
        *,
        products: list[object],
        query: ProductDiscountedQueryParams,
    ) -> list[object]:
        match query.sort:
            case "price_asc":
                return sorted(products, key=lambda product: (product.price, product.name))
            case "price_desc":
                return sorted(products, key=lambda product: (-product.price, product.name))
            case "newest":
                return sorted(products, key=lambda product: (product.created_at, product.name), reverse=True)
            case "discount_desc" | _:
                return sorted(
                    products,
                    key=lambda product: (
                        -((product.old_price - product.price) / product.old_price),
                        product.name,
                    ),
                )


class FakeProductImageRepository:
    def __init__(self, images: list[ProductImageResponse] | None = None) -> None:
        self.images = images if images is not None else [
            ProductImageResponse(id=1, url="/media/products/apple-1.png", sort_order=1),
        ]

    async def get_by_product_id(self, *, session, product_id: int):
        return self.images


def build_category(
    *,
    category_id: int,
    name: str,
    slug: str,
    parent_id: int | None = None,
) -> CategoryShortResponse:
    return CategoryShortResponse(
        id=category_id,
        name=name,
        slug=slug,
        parent_id=parent_id,
        image_url=f"/media/categories/{slug}.png",
        sort_order=10,
        products_count=1,
    )


def build_product(
    *,
    product_id: int,
    name: str,
    slug: str,
    category_id: int | None,
    price: Decimal = Decimal("150.00"),
    old_price: Decimal | None = Decimal("180.00"),
    product_type: str = "weight",
    unit: str = "kg",
    quantity_step: Decimal = Decimal("0.5"),
    min_quantity: Decimal = Decimal("0.5"),
    is_available: bool = True,
    stock_quantity: Decimal = Decimal("10"),
    is_active: bool = True,
    is_deleted: bool = False,
    popularity: int = 0,
    created_at: datetime | None = None,
    description: str | None = "Свежие красные яблоки",
    meta_title: str | None = "Яблоки красные купить онлайн",
    meta_description: str | None = "Свежие красные яблоки с доставкой",
    article: str | None = None,
    barcode: str | None = None,
    search_keywords: str | None = None,
):
    return SimpleNamespace(
        id=product_id,
        name=name,
        slug=slug,
        article=article,
        barcode=barcode,
        preview_image_url=f"/media/products/{slug}.png",
        category_id=category_id,
        category=ProductCategoryShortResponse(id=category_id, name="Яблоки", slug="yabloki") if category_id else None,
        price=price,
        old_price=old_price,
        unit=unit,
        product_type=product_type,
        quantity_step=quantity_step,
        min_quantity=min_quantity,
        is_available=is_available,
        stock_quantity=stock_quantity,
        is_active=is_active,
        is_deleted=is_deleted,
        popularity=popularity,
        created_at=created_at or datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC),
        description=description,
        search_keywords=search_keywords,
        meta_title=meta_title,
        meta_description=meta_description,
    )


def build_product_response(product) -> ProductShortResponse:
    return ProductShortResponse(
        id=product.id,
        name=product.name,
        slug=product.slug,
        preview_image_url=product.preview_image_url,
        price=product.price,
        old_price=product.old_price,
        discount_percent=calculate_discount_percent(price=product.price, old_price=product.old_price),
        unit=product.unit,
        product_type=product.product_type,
        is_available=product.is_available,
        stock_display=build_stock_display(
            is_available=product.is_available,
            stock_quantity=product.stock_quantity,
        ),
        category=product.category,
        created_at=product.created_at,
    )


def build_product_detail_response(product) -> ProductDetailResponse:
    seo = None
    if product.meta_title is not None or product.meta_description is not None:
        seo = ProductSeoResponse(
            meta_title=product.meta_title,
            meta_description=product.meta_description,
        )
    return ProductDetailResponse(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        category=product.category,
        price=product.price,
        old_price=product.old_price,
        discount_percent=calculate_discount_percent(price=product.price, old_price=product.old_price),
        unit=product.unit,
        product_type=product.product_type,
        quantity_step=product.quantity_step,
        min_quantity=product.min_quantity,
        is_available=product.is_available,
        stock_quantity=product.stock_quantity,
        stock_display=build_detailed_stock_display(
            is_available=product.is_available,
            stock_quantity=product.stock_quantity,
            unit=product.unit,
        ),
        images=[],
        seo=seo,
    )


async def execute_get_products(
    *,
    redis_service: FakeRedisService | None = None,
    product_repository: FakeProductRepository | None = None,
    category_repository: FakeCategoryRepository | None = None,
    query: ProductListQueryParams | None = None,
) -> ProductListResponse:
    return await ProductService().get_products(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        product_cache_service=ProductCacheService(),
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        query=query or ProductListQueryParams(),
    )


async def execute_search_products(
    *,
    redis_service: FakeRedisService | None = None,
    product_repository: FakeProductRepository | None = None,
    category_repository: FakeCategoryRepository | None = None,
    query: ProductSearchQueryParams | None = None,
) -> ProductSearchResponse:
    return await ProductService().search_products(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        product_cache_service=ProductCacheService(),
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        query=query or ProductSearchQueryParams(q="яблоки"),
    )


async def execute_get_popular_products(
    *,
    redis_service: FakeRedisService | None = None,
    product_repository: FakeProductRepository | None = None,
    category_repository: FakeCategoryRepository | None = None,
    query: ProductPopularQueryParams | None = None,
) -> ProductPopularResponse:
    return await ProductService().get_popular_products(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        product_cache_service=ProductCacheService(),
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        query=query or ProductPopularQueryParams(),
    )


async def execute_get_discounted_products(
    *,
    redis_service: FakeRedisService | None = None,
    product_repository: FakeProductRepository | None = None,
    category_repository: FakeCategoryRepository | None = None,
    query: ProductDiscountedQueryParams | None = None,
) -> ProductDiscountedResponse:
    return await ProductService().get_discounted_products(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        product_cache_service=ProductCacheService(),
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        query=query or ProductDiscountedQueryParams(),
    )


async def execute_get_new_products(
    *,
    redis_service: FakeRedisService | None = None,
    product_repository: FakeProductRepository | None = None,
    category_repository: FakeCategoryRepository | None = None,
    query: ProductNewQueryParams | None = None,
) -> ProductNewResponse:
    return await ProductService().get_new_products(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        product_cache_service=ProductCacheService(),
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        query=query or ProductNewQueryParams(),
    )


async def execute_get_similar_products(
    *,
    redis_service: FakeRedisService | None = None,
    product_repository: FakeProductRepository | None = None,
    product_id: int = 55,
    query: ProductSimilarQueryParams | None = None,
) -> ProductSimilarResponse:
    return await ProductService().get_similar_products(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        product_cache_service=ProductCacheService(),
        product_repository=product_repository or FakeProductRepository(),
        product_id=product_id,
        query=query or ProductSimilarQueryParams(),
    )


async def execute_get_product_by_id(
    *,
    redis_service: FakeRedisService | None = None,
    product_repository: FakeProductRepository | None = None,
    product_image_repository: FakeProductImageRepository | None = None,
    category_repository: FakeCategoryRepository | None = None,
    product_id: int = 55,
    query: ProductDetailQueryParams | None = None,
) -> ProductDetailResponse:
    return await ProductService().get_product_by_id(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        product_cache_service=ProductCacheService(),
        product_repository=product_repository or FakeProductRepository(),
        product_image_repository=product_image_repository or FakeProductImageRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        product_id=product_id,
        query=query or ProductDetailQueryParams(),
    )


async def execute_get_product_by_slug(
    *,
    redis_service: FakeRedisService | None = None,
    product_repository: FakeProductRepository | None = None,
    product_image_repository: FakeProductImageRepository | None = None,
    category_repository: FakeCategoryRepository | None = None,
    slug: str = "yabloki-krasnye",
    query: ProductDetailQueryParams | None = None,
) -> ProductDetailResponse:
    return await ProductService().get_product_by_slug(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        product_cache_service=ProductCacheService(),
        product_repository=product_repository or FakeProductRepository(),
        product_image_repository=product_image_repository or FakeProductImageRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        slug=slug,
        query=query or ProductDetailQueryParams(),
    )


@pytest.mark.asyncio
async def test_get_product_by_id_from_postgresql_success() -> None:
    response = await execute_get_product_by_id()

    assert response.id == 55
    assert response.slug == "yabloki-krasnye"
    assert response.description == "Свежие красные яблоки"
    assert response.category is not None
    assert response.quantity_step == Decimal("0.5")
    assert response.min_quantity == Decimal("0.5")
    assert response.images[0].url == "/media/products/apple-1.png"
    assert response.seo is not None
    assert response.seo.meta_title == "Яблоки красные купить онлайн"


@pytest.mark.asyncio
async def test_get_product_by_id_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = ProductDetailQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = build_product_detail_response(
        build_product(product_id=55, name="Яблоки красные", slug="yabloki-krasnye", category_id=11),
    )
    redis_service.values[f"products:detail:55:{query_hash}"] = cached_response.model_dump_json()
    product_repository = FakeProductRepository(products=[])

    response = await execute_get_product_by_id(
        redis_service=redis_service,
        product_repository=product_repository,
        query=query,
    )

    assert response.id == 55
    assert product_repository.query is None


@pytest.mark.asyncio
async def test_get_product_by_id_not_found() -> None:
    with pytest.raises(ProductNotFoundError):
        await execute_get_product_by_id(
            product_repository=FakeProductRepository(products=[]),
            product_id=999,
        )


@pytest.mark.asyncio
async def test_get_product_by_id_inactive_product_not_found() -> None:
    with pytest.raises(ProductNotFoundError):
        await execute_get_product_by_id(
            product_repository=FakeProductRepository(
                products=[
                    build_product(
                        product_id=55,
                        name="Скрытый",
                        slug="hidden",
                        category_id=11,
                        is_active=False,
                    ),
                ],
            ),
        )


@pytest.mark.asyncio
async def test_get_product_by_id_deleted_product_not_found() -> None:
    with pytest.raises(ProductNotFoundError):
        await execute_get_product_by_id(
            product_repository=FakeProductRepository(
                products=[
                    build_product(
                        product_id=55,
                        name="Удалённый",
                        slug="deleted",
                        category_id=11,
                        is_deleted=True,
                    ),
                ],
            ),
        )


@pytest.mark.asyncio
async def test_get_product_by_id_calculates_discount() -> None:
    response = await execute_get_product_by_id(
        product_repository=FakeProductRepository(
            products=[
                build_product(
                    product_id=55,
                    name="Яблоки красные",
                    slug="yabloki-krasnye",
                    category_id=11,
                    price=Decimal("150.00"),
                    old_price=Decimal("180.00"),
                ),
            ],
        ),
    )

    assert response.discount_percent == 17


@pytest.mark.asyncio
async def test_get_product_by_id_builds_stock_display() -> None:
    response = await execute_get_product_by_id(
        product_repository=FakeProductRepository(
            products=[
                build_product(
                    product_id=55,
                    name="Яблоки красные",
                    slug="yabloki-krasnye",
                    category_id=11,
                    stock_quantity=Decimal("2.5"),
                    unit="kg",
                ),
            ],
        ),
    )

    assert response.stock_display == "Осталось 2.5 kg"


@pytest.mark.asyncio
async def test_get_product_by_id_with_breadcrumbs_returns_parent_chain() -> None:
    response = await execute_get_product_by_id(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
            ],
        ),
    )

    assert response.breadcrumbs is not None
    assert [breadcrumb.id for breadcrumb in response.breadcrumbs] == [1, 11]


@pytest.mark.asyncio
async def test_get_product_by_id_with_similar_returns_similar_products() -> None:
    response = await execute_get_product_by_id(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки красные", slug="yabloki-krasnye", category_id=11),
                build_product(product_id=56, name="Яблоки зелёные", slug="yabloki-zelenye", category_id=11),
                build_product(product_id=57, name="Бананы", slug="banany", category_id=1),
            ],
        ),
        query=ProductDetailQueryParams(with_similar=True),
    )

    assert response.similar is not None
    assert [product.id for product in response.similar] == [56]


@pytest.mark.asyncio
async def test_get_product_by_id_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductDetailQueryParams(with_similar=True)

    await execute_get_product_by_id(redis_service=redis_service, query=query)

    cache_key = f"products:detail:55:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.detail_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_product_by_slug_from_postgresql_success() -> None:
    product_repository = FakeProductRepository()

    response = await execute_get_product_by_slug(
        product_repository=product_repository,
        slug=" YABLOKI-KRASNYE ",
    )

    assert response.id == 55
    assert response.slug == "yabloki-krasnye"
    assert response.images[0].url == "/media/products/apple-1.png"
    assert response.category is not None
    assert response.seo is not None
    assert product_repository.requested_slug == "yabloki-krasnye"


@pytest.mark.asyncio
async def test_get_product_by_slug_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = ProductDetailQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = build_product_detail_response(
        build_product(product_id=55, name="Яблоки красные", slug="yabloki-krasnye", category_id=11),
    )
    redis_service.values[f"products:slug:yabloki-krasnye:{query_hash}"] = cached_response.model_dump_json()
    product_repository = FakeProductRepository(products=[])

    response = await execute_get_product_by_slug(
        redis_service=redis_service,
        product_repository=product_repository,
        slug="YABLOKI-KRASNYE",
        query=query,
    )

    assert response.id == 55
    assert product_repository.requested_slug is None


def test_product_slug_validation_and_normalization() -> None:
    assert normalize_slug(" YABLOKI-KRASNYE_1 ") == "yabloki-krasnye_1"
    assert validate_slug("yabloki-krasnye_1")
    assert validate_slug("a" * 200)
    assert not validate_slug("яблоки")
    assert not validate_slug("a" * 201)


@pytest.mark.asyncio
async def test_get_product_by_slug_not_found() -> None:
    with pytest.raises(ProductNotFoundError):
        await execute_get_product_by_slug(
            product_repository=FakeProductRepository(products=[]),
            slug="missing-product",
        )


@pytest.mark.asyncio
async def test_get_product_by_slug_inactive_product_not_found() -> None:
    with pytest.raises(ProductNotFoundError):
        await execute_get_product_by_slug(
            product_repository=FakeProductRepository(
                products=[
                    build_product(
                        product_id=55,
                        name="Скрытый",
                        slug="hidden",
                        category_id=11,
                        is_active=False,
                    ),
                ],
            ),
            slug="hidden",
        )


@pytest.mark.asyncio
async def test_get_product_by_slug_deleted_product_not_found() -> None:
    with pytest.raises(ProductNotFoundError):
        await execute_get_product_by_slug(
            product_repository=FakeProductRepository(
                products=[
                    build_product(
                        product_id=55,
                        name="Удалённый",
                        slug="deleted",
                        category_id=11,
                        is_deleted=True,
                    ),
                ],
            ),
            slug="deleted",
        )


@pytest.mark.asyncio
async def test_get_product_by_slug_calculates_discount() -> None:
    response = await execute_get_product_by_slug(
        product_repository=FakeProductRepository(
            products=[
                build_product(
                    product_id=55,
                    name="Яблоки красные",
                    slug="yabloki-krasnye",
                    category_id=11,
                    price=Decimal("150.00"),
                    old_price=Decimal("180.00"),
                ),
            ],
        ),
    )

    assert response.discount_percent == 17


@pytest.mark.asyncio
async def test_get_product_by_slug_builds_stock_display() -> None:
    response = await execute_get_product_by_slug(
        product_repository=FakeProductRepository(
            products=[
                build_product(
                    product_id=55,
                    name="Яблоки красные",
                    slug="yabloki-krasnye",
                    category_id=11,
                    stock_quantity=Decimal("0"),
                    is_available=False,
                ),
            ],
        ),
    )

    assert response.stock_display == "Нет в наличии"


@pytest.mark.asyncio
async def test_get_product_by_slug_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductDetailQueryParams(with_similar=True)

    await execute_get_product_by_slug(redis_service=redis_service, query=query)

    cache_key = f"products:slug:yabloki-krasnye:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.slug_cache_ttl_seconds


@pytest.mark.asyncio
async def test_search_products_success() -> None:
    response = await execute_search_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки красные", slug="yabloki-krasnye", category_id=11),
                build_product(product_id=56, name="Груши", slug="grushi", category_id=1, description="Сочные груши"),
            ],
        ),
        query=ProductSearchQueryParams(q=" яблоки "),
    )

    assert response.query == "яблоки"
    assert response.total == 1
    assert response.items[0].id == 55


def test_search_products_empty_query_error() -> None:
    with pytest.raises(ValueError):
        ProductSearchQueryParams(q="   ")


def test_search_products_short_query_error() -> None:
    with pytest.raises(ValueError):
        ProductSearchQueryParams(q="я")


@pytest.mark.asyncio
async def test_search_products_excludes_inactive_products() -> None:
    response = await execute_search_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки", slug="active", category_id=11),
                build_product(product_id=56, name="Яблоки скрытые", slug="inactive", category_id=11, is_active=False),
            ],
        ),
        query=ProductSearchQueryParams(q="яблоки"),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_search_products_excludes_deleted_products() -> None:
    response = await execute_search_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки", slug="active", category_id=11),
                build_product(product_id=56, name="Яблоки удалённые", slug="deleted", category_id=11, is_deleted=True),
            ],
        ),
        query=ProductSearchQueryParams(q="яблоки"),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_search_products_filter_in_stock_true() -> None:
    response = await execute_search_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки есть", slug="in-stock", category_id=11),
                build_product(product_id=56, name="Яблоки нет", slug="out-stock", category_id=11, stock_quantity=Decimal("0")),
            ],
        ),
        query=ProductSearchQueryParams(q="яблоки", in_stock=True),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_search_products_filter_category_id() -> None:
    category_repository = FakeCategoryRepository(
        categories=[
            build_category(category_id=5, name="Фрукты", slug="frukty"),
            build_category(category_id=15, name="Яблоки", slug="yabloki", parent_id=5),
        ],
    )
    product_repository = FakeProductRepository(
        products=[
            build_product(product_id=55, name="Яблоки красные", slug="red", category_id=15),
            build_product(product_id=56, name="Яблоки овощные", slug="other", category_id=9),
        ],
    )

    response = await execute_search_products(
        category_repository=category_repository,
        product_repository=product_repository,
        query=ProductSearchQueryParams(q="яблоки", category_id=5),
    )

    assert [product.id for product in response.items] == [55]
    assert product_repository.category_ids is None


@pytest.mark.asyncio
async def test_search_products_pagination() -> None:
    response = await execute_search_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Яблоки A", slug="a", category_id=11),
                build_product(product_id=2, name="Яблоки B", slug="b", category_id=11),
                build_product(product_id=3, name="Яблоки C", slug="c", category_id=11),
            ],
        ),
        query=ProductSearchQueryParams(q="яблоки", page=2, limit=1),
    )

    assert response.total == 3
    assert response.page == 2
    assert response.pages == 3
    assert [product.id for product in response.items] == [2]


@pytest.mark.asyncio
async def test_search_products_sort_relevance() -> None:
    response = await execute_search_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(
                    product_id=55,
                    name="Красные фрукты",
                    slug="red-fruits",
                    category_id=11,
                    search_keywords="яблоки",
                    popularity=100,
                ),
                build_product(
                    product_id=56,
                    name="Яблоки красные",
                    slug="red-apples",
                    category_id=11,
                    popularity=1,
                ),
            ],
        ),
        query=ProductSearchQueryParams(q="яблоки", sort="relevance"),
    )

    assert [product.id for product in response.items] == [56, 55]


@pytest.mark.asyncio
async def test_search_products_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = ProductSearchQueryParams(q="яблоки")
    query_hash = build_query_hash(query.model_dump())
    cached_response = ProductSearchResponse.build(
        query="яблоки",
        items=[build_product_response(build_product(product_id=55, name="Яблоки", slug="yabloki", category_id=11))],
        total=1,
        page=1,
        limit=24,
    )
    redis_service.values[f"products:search:{query_hash}"] = cached_response.model_dump_json()
    product_repository = FakeProductRepository(products=[])

    response = await execute_search_products(
        redis_service=redis_service,
        product_repository=product_repository,
        query=query,
    )

    assert response.total == 1
    assert product_repository.query is None


@pytest.mark.asyncio
async def test_search_products_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductSearchQueryParams(q=" яблоки ")

    await execute_search_products(redis_service=redis_service, query=query)

    normalized_query = query.model_copy(update={"q": "яблоки"})
    cache_key = f"products:search:{build_query_hash(normalized_query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.search_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_popular_products_success() -> None:
    response = await execute_get_popular_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Популярный", slug="popular", category_id=11, popularity=100),
                build_product(product_id=56, name="Обычный", slug="regular", category_id=11, popularity=10),
            ],
        ),
    )

    assert response.total == 2
    assert [product.id for product in response.items] == [55, 56]


@pytest.mark.asyncio
async def test_get_popular_products_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = ProductPopularQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = ProductPopularResponse(
        items=[build_product_response(build_product(product_id=55, name="Популярный", slug="popular", category_id=11))],
        total=1,
    )
    redis_service.values[f"products:popular:{query_hash}"] = cached_response.model_dump_json()
    product_repository = FakeProductRepository(products=[])

    response = await execute_get_popular_products(
        redis_service=redis_service,
        product_repository=product_repository,
        query=query,
    )

    assert response.total == 1
    assert product_repository.query is None


@pytest.mark.asyncio
async def test_get_popular_products_limit_works() -> None:
    response = await execute_get_popular_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="A", slug="a", category_id=11, popularity=30),
                build_product(product_id=2, name="B", slug="b", category_id=11, popularity=20),
                build_product(product_id=3, name="C", slug="c", category_id=11, popularity=10),
            ],
        ),
        query=ProductPopularQueryParams(limit=2),
    )

    assert response.total == 2
    assert [product.id for product in response.items] == [1, 2]


@pytest.mark.asyncio
async def test_get_popular_products_filter_category_id() -> None:
    category_repository = FakeCategoryRepository(
        categories=[
            build_category(category_id=5, name="Фрукты", slug="frukty"),
            build_category(category_id=15, name="Яблоки", slug="yabloki", parent_id=5),
        ],
    )
    response = await execute_get_popular_products(
        category_repository=category_repository,
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки", slug="apples", category_id=15, popularity=100),
                build_product(product_id=56, name="Овощи", slug="vegetables", category_id=9, popularity=200),
            ],
        ),
        query=ProductPopularQueryParams(category_id=5),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_popular_products_in_stock_true_excludes_unavailable() -> None:
    response = await execute_get_popular_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Есть", slug="in-stock", category_id=11, popularity=10),
                build_product(
                    product_id=56,
                    name="Нет",
                    slug="out-stock",
                    category_id=11,
                    popularity=100,
                    stock_quantity=Decimal("0"),
                ),
            ],
        ),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_popular_products_excludes_inactive_products() -> None:
    response = await execute_get_popular_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Активный", slug="active", category_id=11, popularity=10),
                build_product(
                    product_id=56,
                    name="Скрытый",
                    slug="inactive",
                    category_id=11,
                    popularity=100,
                    is_active=False,
                ),
            ],
        ),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_popular_products_excludes_deleted_products() -> None:
    response = await execute_get_popular_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Активный", slug="active", category_id=11, popularity=10),
                build_product(
                    product_id=56,
                    name="Удалённый",
                    slug="deleted",
                    category_id=11,
                    popularity=100,
                    is_deleted=True,
                ),
            ],
        ),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_popular_products_sorts_by_popularity() -> None:
    response = await execute_get_popular_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Low", slug="low", category_id=11, popularity=1),
                build_product(product_id=2, name="High", slug="high", category_id=11, popularity=100),
                build_product(product_id=3, name="Middle", slug="middle", category_id=11, popularity=50),
            ],
        ),
        query=ProductPopularQueryParams(in_stock=False),
    )

    assert [product.id for product in response.items] == [2, 3, 1]


@pytest.mark.asyncio
async def test_get_popular_products_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductPopularQueryParams(limit=2, period_days=7)

    await execute_get_popular_products(redis_service=redis_service, query=query)

    cache_key = f"products:popular:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.popular_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_discounted_products_success() -> None:
    response = await execute_get_discounted_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Скидка", slug="discount", category_id=11),
                build_product(product_id=56, name="Без скидки", slug="regular", category_id=11, old_price=None),
            ],
        ),
    )

    assert response.total == 1
    assert response.page == 1
    assert response.limit == 24
    assert response.pages == 1
    assert response.items[0].id == 55
    assert response.items[0].discount_percent == 17


@pytest.mark.asyncio
async def test_get_discounted_products_excludes_products_without_discount() -> None:
    response = await execute_get_discounted_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Без old_price", slug="no-old", category_id=11, old_price=None),
                build_product(
                    product_id=56,
                    name="old_price ниже цены",
                    slug="bad-old",
                    category_id=11,
                    price=Decimal("200"),
                    old_price=Decimal("180"),
                ),
            ],
        ),
    )

    assert response.total == 0
    assert response.items == []


@pytest.mark.asyncio
async def test_get_discounted_products_ignores_expired_and_future_discounts_for_mvp() -> None:
    response = await execute_get_discounted_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Активная скидка", slug="active-discount", category_id=11),
                build_product(product_id=56, name="Нет активной скидки", slug="no-discount", category_id=11, old_price=None),
            ],
        ),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_discounted_products_in_stock_true_excludes_unavailable() -> None:
    response = await execute_get_discounted_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Есть", slug="in-stock", category_id=11),
                build_product(
                    product_id=56,
                    name="Нет",
                    slug="out-stock",
                    category_id=11,
                    stock_quantity=Decimal("0"),
                ),
            ],
        ),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_discounted_products_sort_discount_desc() -> None:
    response = await execute_get_discounted_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(
                    product_id=55,
                    name="Скидка 10",
                    slug="discount-10",
                    category_id=11,
                    price=Decimal("90"),
                    old_price=Decimal("100"),
                ),
                build_product(
                    product_id=56,
                    name="Скидка 50",
                    slug="discount-50",
                    category_id=11,
                    price=Decimal("50"),
                    old_price=Decimal("100"),
                ),
            ],
        ),
        query=ProductDiscountedQueryParams(sort="discount_desc"),
    )

    assert [product.id for product in response.items] == [56, 55]


@pytest.mark.asyncio
async def test_get_discounted_products_pagination() -> None:
    response = await execute_get_discounted_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="A", slug="a", category_id=11),
                build_product(product_id=2, name="B", slug="b", category_id=11),
                build_product(product_id=3, name="C", slug="c", category_id=11),
            ],
        ),
        query=ProductDiscountedQueryParams(page=2, limit=1),
    )

    assert response.total == 3
    assert response.page == 2
    assert response.pages == 3
    assert [product.id for product in response.items] == [2]


@pytest.mark.asyncio
async def test_get_discounted_products_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = ProductDiscountedQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = ProductDiscountedResponse.build(
        items=[build_product_response(build_product(product_id=55, name="Скидка", slug="discount", category_id=11))],
        total=1,
        page=1,
        limit=24,
    )
    redis_service.values[f"products:discounted:{query_hash}"] = cached_response.model_dump_json()
    product_repository = FakeProductRepository(products=[])

    response = await execute_get_discounted_products(
        redis_service=redis_service,
        product_repository=product_repository,
        query=query,
    )

    assert response.total == 1
    assert product_repository.query is None


@pytest.mark.asyncio
async def test_get_discounted_products_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductDiscountedQueryParams(page=1, limit=2)

    await execute_get_discounted_products(redis_service=redis_service, query=query)

    cache_key = f"products:discounted:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.discounted_cache_ttl_seconds


@pytest.mark.asyncio
async def test_discounted_cache_invalidates_on_discount_change() -> None:
    redis_service = FakeRedisService()

    await ProductCacheService().invalidate_discounted(redis_service=redis_service)

    assert redis_service.deleted_patterns == ["products:discounted:*"]


@pytest.mark.asyncio
async def test_get_new_products_success() -> None:
    response = await execute_get_new_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=90, name="Груши сезонные", slug="grushi-sezonnye", category_id=11),
                build_product(
                    product_id=91,
                    name="Старый товар",
                    slug="old-product",
                    category_id=11,
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ],
        ),
    )

    assert response.total == 1
    assert response.items[0].id == 90
    assert response.items[0].created_at == datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_get_new_products_sort_created_at_desc() -> None:
    response = await execute_get_new_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Old", slug="old", category_id=11, created_at=datetime(2026, 5, 1, tzinfo=UTC)),
                build_product(product_id=2, name="New", slug="new", category_id=11, created_at=datetime(2026, 5, 13, tzinfo=UTC)),
            ],
        ),
        query=ProductNewQueryParams(days=30, in_stock=False),
    )

    assert [product.id for product in response.items] == [2, 1]


@pytest.mark.asyncio
async def test_get_new_products_limit_works() -> None:
    response = await execute_get_new_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="A", slug="a", category_id=11, created_at=datetime(2026, 5, 13, tzinfo=UTC)),
                build_product(product_id=2, name="B", slug="b", category_id=11, created_at=datetime(2026, 5, 12, tzinfo=UTC)),
            ],
        ),
        query=ProductNewQueryParams(limit=1, in_stock=False),
    )

    assert response.total == 1
    assert [product.id for product in response.items] == [1]


@pytest.mark.asyncio
async def test_get_new_products_days_works() -> None:
    response = await execute_get_new_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Today", slug="today", category_id=11, created_at=datetime(2026, 5, 14, tzinfo=UTC)),
                build_product(product_id=2, name="Earlier", slug="earlier", category_id=11, created_at=datetime(2026, 5, 10, tzinfo=UTC)),
            ],
        ),
        query=ProductNewQueryParams(days=2, in_stock=False),
    )

    assert [product.id for product in response.items] == [1]


@pytest.mark.asyncio
async def test_get_new_products_filter_category_id() -> None:
    category_repository = FakeCategoryRepository(
        categories=[
            build_category(category_id=5, name="Фрукты", slug="frukty"),
            build_category(category_id=15, name="Яблоки", slug="yabloki", parent_id=5),
        ],
    )
    response = await execute_get_new_products(
        category_repository=category_repository,
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки", slug="apples", category_id=15),
                build_product(product_id=56, name="Овощи", slug="vegetables", category_id=9),
            ],
        ),
        query=ProductNewQueryParams(category_id=5),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_new_products_in_stock_true_excludes_unavailable() -> None:
    response = await execute_get_new_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Есть", slug="in-stock", category_id=11),
                build_product(
                    product_id=56,
                    name="Нет",
                    slug="out-stock",
                    category_id=11,
                    stock_quantity=Decimal("0"),
                ),
            ],
        ),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_new_products_excludes_inactive_products() -> None:
    response = await execute_get_new_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Активный", slug="active", category_id=11),
                build_product(product_id=56, name="Скрытый", slug="inactive", category_id=11, is_active=False),
            ],
        ),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_new_products_excludes_deleted_products() -> None:
    response = await execute_get_new_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Активный", slug="active", category_id=11),
                build_product(product_id=56, name="Удалённый", slug="deleted", category_id=11, is_deleted=True),
            ],
        ),
    )

    assert [product.id for product in response.items] == [55]


@pytest.mark.asyncio
async def test_get_new_products_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductNewQueryParams(limit=2, days=7)

    await execute_get_new_products(redis_service=redis_service, query=query)

    cache_key = f"products:new:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.new_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_similar_products_success() -> None:
    response = await execute_get_similar_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Яблоки красные", slug="red-apples", category_id=11),
                build_product(product_id=56, name="Яблоки зелёные", slug="green-apples", category_id=11),
            ],
        ),
    )

    assert response.total == 1
    assert response.items[0].id == 56


@pytest.mark.asyncio
async def test_get_similar_products_excludes_source_product() -> None:
    response = await execute_get_similar_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Исходный", slug="source", category_id=11),
                build_product(product_id=56, name="Похожий", slug="similar", category_id=11),
            ],
        ),
    )

    assert 55 not in {product.id for product in response.items}


@pytest.mark.asyncio
async def test_get_similar_products_source_not_found() -> None:
    with pytest.raises(ProductNotFoundError):
        await execute_get_similar_products(
            product_repository=FakeProductRepository(products=[]),
            product_id=999,
        )


@pytest.mark.asyncio
async def test_get_similar_products_excludes_inactive_products() -> None:
    response = await execute_get_similar_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Исходный", slug="source", category_id=11),
                build_product(product_id=56, name="Скрытый", slug="inactive", category_id=11, is_active=False),
                build_product(product_id=57, name="Активный", slug="active", category_id=11),
            ],
        ),
    )

    assert [product.id for product in response.items] == [57]


@pytest.mark.asyncio
async def test_get_similar_products_excludes_deleted_products() -> None:
    response = await execute_get_similar_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Исходный", slug="source", category_id=11),
                build_product(product_id=56, name="Удалённый", slug="deleted", category_id=11, is_deleted=True),
                build_product(product_id=57, name="Активный", slug="active", category_id=11),
            ],
        ),
    )

    assert [product.id for product in response.items] == [57]


@pytest.mark.asyncio
async def test_get_similar_products_in_stock_true_excludes_unavailable() -> None:
    response = await execute_get_similar_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Исходный", slug="source", category_id=11),
                build_product(product_id=56, name="Нет", slug="out-stock", category_id=11, stock_quantity=Decimal("0")),
                build_product(product_id=57, name="Есть", slug="in-stock", category_id=11),
            ],
        ),
    )

    assert [product.id for product in response.items] == [57]


@pytest.mark.asyncio
async def test_get_similar_products_limit_works() -> None:
    response = await execute_get_similar_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Исходный", slug="source", category_id=11),
                build_product(product_id=56, name="A", slug="a", category_id=11, popularity=30),
                build_product(product_id=57, name="B", slug="b", category_id=11, popularity=20),
            ],
        ),
        query=ProductSimilarQueryParams(limit=1),
    )

    assert response.total == 1
    assert [product.id for product in response.items] == [56]


@pytest.mark.asyncio
async def test_get_similar_products_uses_same_category() -> None:
    response = await execute_get_similar_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=55, name="Исходный", slug="source", category_id=11),
                build_product(product_id=56, name="Та же категория", slug="same", category_id=11),
                build_product(product_id=57, name="Другая категория", slug="other", category_id=1),
            ],
        ),
    )

    assert [product.id for product in response.items] == [56]


@pytest.mark.asyncio
async def test_get_similar_products_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductSimilarQueryParams(limit=2)

    await execute_get_similar_products(redis_service=redis_service, query=query)

    cache_key = f"products:similar:55:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.similar_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_similar_products_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = ProductSimilarQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = ProductSimilarResponse(
        items=[build_product_response(build_product(product_id=56, name="Похожий", slug="similar", category_id=11))],
        total=1,
    )
    redis_service.values[f"products:similar:55:{query_hash}"] = cached_response.model_dump_json()
    product_repository = FakeProductRepository(products=[])

    response = await execute_get_similar_products(
        redis_service=redis_service,
        product_repository=product_repository,
        query=query,
    )

    assert response.total == 1
    assert response.items[0].id == 56


@pytest.mark.asyncio
async def test_get_products_from_postgresql_success() -> None:
    response = await execute_get_products()

    assert response.total == 2
    assert response.page == 1
    assert response.limit == 24
    assert response.pages == 1
    assert response.items[0].slug == "banany"
    assert response.items[0].category is not None


@pytest.mark.asyncio
async def test_get_products_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = ProductListQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = ProductListResponse.build(
        items=[build_product_response(build_product(product_id=55, name="Яблоки", slug="yabloki", category_id=11))],
        total=1,
        page=1,
        limit=24,
    )
    redis_service.values[f"products:list:{query_hash}"] = cached_response.model_dump_json()
    product_repository = FakeProductRepository(products=[])

    response = await execute_get_products(
        redis_service=redis_service,
        product_repository=product_repository,
        query=query,
    )

    assert response.total == 1
    assert product_repository.query is None


@pytest.mark.asyncio
async def test_get_products_pagination_page_limit() -> None:
    product_repository = FakeProductRepository(
        products=[
            build_product(product_id=1, name="A", slug="a", category_id=1),
            build_product(product_id=2, name="B", slug="b", category_id=1),
            build_product(product_id=3, name="C", slug="c", category_id=1),
        ],
    )

    response = await execute_get_products(
        product_repository=product_repository,
        query=ProductListQueryParams(page=2, limit=1),
    )

    assert response.total == 3
    assert response.page == 2
    assert response.limit == 1
    assert response.pages == ceil(3 / 1)
    assert [product.id for product in response.items] == [2]


@pytest.mark.asyncio
async def test_get_products_filter_by_category_id_includes_children() -> None:
    product_repository = FakeProductRepository(
        products=[
            build_product(product_id=1, name="Фрукты", slug="frukty-product", category_id=1),
            build_product(product_id=2, name="Яблоки", slug="yabloki-product", category_id=11),
            build_product(product_id=3, name="Овощи", slug="ovoshchi-product", category_id=2),
        ],
    )

    response = await execute_get_products(
        product_repository=product_repository,
        query=ProductListQueryParams(category_id=1),
    )

    assert {product.id for product in response.items} == {1, 2}
    assert product_repository.category_ids == {1, 11}


@pytest.mark.asyncio
async def test_get_products_with_page_limit_category_id_and_in_stock_true() -> None:
    category_repository = FakeCategoryRepository(
        categories=[
            build_category(category_id=5, name="Фрукты", slug="frukty"),
            build_category(category_id=15, name="Яблоки", slug="yabloki", parent_id=5),
        ],
    )
    product_repository = FakeProductRepository(
        products=[
            build_product(
                product_id=55,
                name="Яблоки красные",
                slug="yabloki-krasnye",
                category_id=5,
                old_price=None,
            ),
            build_product(
                product_id=56,
                name="Яблоки зелёные",
                slug="yabloki-zelenye",
                category_id=15,
                old_price=None,
            ),
            build_product(
                product_id=57,
                name="Нет в наличии",
                slug="out-of-stock",
                category_id=5,
                stock_quantity=Decimal("0"),
            ),
            build_product(
                product_id=58,
                name="Овощи",
                slug="ovoshchi",
                category_id=9,
            ),
        ],
    )

    response = await execute_get_products(
        category_repository=category_repository,
        product_repository=product_repository,
        query=ProductListQueryParams(page=1, limit=24, category_id=5, in_stock=True),
    )

    assert response.page == 1
    assert response.limit == 24
    assert response.total == 2
    assert response.pages == 1
    assert {product.id for product in response.items} == {55, 56}
    assert all(product.is_available for product in response.items)
    assert all(product.stock_display == "В наличии" for product in response.items)
    assert response.items[0].old_price is None
    assert response.items[0].discount_percent is None
    assert product_repository.category_ids == {5, 15}


@pytest.mark.asyncio
async def test_get_products_filter_by_category_slug() -> None:
    category_repository = FakeCategoryRepository()
    product_repository = FakeProductRepository(
        products=[
            build_product(product_id=1, name="Яблоки", slug="yabloki-product", category_id=11),
            build_product(product_id=2, name="Овощи", slug="ovoshchi-product", category_id=2),
        ],
    )

    response = await execute_get_products(
        category_repository=category_repository,
        product_repository=product_repository,
        query=ProductListQueryParams(category_slug=" YABLOKI "),
    )

    assert [product.id for product in response.items] == [1]
    assert category_repository.requested_slug == "yabloki"


@pytest.mark.asyncio
async def test_get_products_category_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_products(
            category_repository=FakeCategoryRepository(categories=[]),
            query=ProductListQueryParams(category_id=999),
        )


@pytest.mark.asyncio
async def test_get_products_requested_category_id_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_products(
            category_repository=FakeCategoryRepository(
                categories=[build_category(category_id=1, name="Фрукты", slug="frukty")],
            ),
            query=ProductListQueryParams(page=1, limit=24, category_id=5, in_stock=True),
        )


@pytest.mark.asyncio
async def test_get_products_filter_in_stock_true() -> None:
    response = await execute_get_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Есть", slug="in-stock", category_id=1),
                build_product(product_id=2, name="Нет", slug="out-stock", category_id=1, stock_quantity=Decimal("0")),
            ],
        ),
        query=ProductListQueryParams(in_stock=True),
    )

    assert [product.id for product in response.items] == [1]


@pytest.mark.asyncio
async def test_get_products_filter_has_discount_true() -> None:
    response = await execute_get_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Скидка", slug="discount", category_id=1),
                build_product(product_id=2, name="Без скидки", slug="no-discount", category_id=1, old_price=None),
            ],
        ),
        query=ProductListQueryParams(has_discount=True),
    )

    assert [product.id for product in response.items] == [1]
    assert response.items[0].discount_percent == 17


@pytest.mark.asyncio
async def test_get_products_filter_product_type() -> None:
    response = await execute_get_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Весовой", slug="weight", category_id=1, product_type="weight"),
                build_product(product_id=2, name="Штучный", slug="piece", category_id=1, product_type="piece"),
            ],
        ),
        query=ProductListQueryParams(product_type="piece"),
    )

    assert [product.id for product in response.items] == [2]


@pytest.mark.asyncio
async def test_get_products_sort_price_asc() -> None:
    response = await execute_get_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="B", slug="b", category_id=1, price=Decimal("200")),
                build_product(product_id=2, name="A", slug="a", category_id=1, price=Decimal("100")),
            ],
        ),
        query=ProductListQueryParams(sort="price_asc"),
    )

    assert [product.id for product in response.items] == [2, 1]


@pytest.mark.asyncio
async def test_get_products_sort_price_desc() -> None:
    response = await execute_get_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="B", slug="b", category_id=1, price=Decimal("200")),
                build_product(product_id=2, name="A", slug="a", category_id=1, price=Decimal("100")),
            ],
        ),
        query=ProductListQueryParams(sort="price_desc"),
    )

    assert [product.id for product in response.items] == [1, 2]


@pytest.mark.asyncio
async def test_get_products_sort_newest() -> None:
    response = await execute_get_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Old", slug="old", category_id=1, created_at=datetime(2026, 5, 1, tzinfo=UTC)),
                build_product(product_id=2, name="New", slug="new", category_id=1, created_at=datetime(2026, 5, 2, tzinfo=UTC)),
            ],
        ),
        query=ProductListQueryParams(sort="newest"),
    )

    assert [product.id for product in response.items] == [2, 1]


@pytest.mark.asyncio
async def test_get_products_excludes_inactive_products() -> None:
    response = await execute_get_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Активный", slug="active", category_id=1),
                build_product(product_id=2, name="Скрытый", slug="inactive", category_id=1, is_active=False),
            ],
        ),
    )

    assert [product.id for product in response.items] == [1]


@pytest.mark.asyncio
async def test_get_products_excludes_deleted_products() -> None:
    response = await execute_get_products(
        product_repository=FakeProductRepository(
            products=[
                build_product(product_id=1, name="Активный", slug="active", category_id=1),
                build_product(product_id=2, name="Удалённый", slug="deleted", category_id=1, is_deleted=True),
            ],
        ),
    )

    assert [product.id for product in response.items] == [1]


@pytest.mark.asyncio
async def test_get_products_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductListQueryParams(category_id=1, sort="price_asc")

    await execute_get_products(redis_service=redis_service, query=query)

    cache_key = f"products:list:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.list_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_products_with_category_and_in_stock_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = ProductListQueryParams(page=1, limit=24, category_id=5, in_stock=True)

    await execute_get_products(
        redis_service=redis_service,
        category_repository=FakeCategoryRepository(
            categories=[build_category(category_id=5, name="Фрукты", slug="frukty")],
        ),
        product_repository=FakeProductRepository(
            products=[build_product(product_id=55, name="Яблоки красные", slug="yabloki-krasnye", category_id=5)],
        ),
        query=query,
    )

    cache_key = f"products:list:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.products.list_cache_ttl_seconds
