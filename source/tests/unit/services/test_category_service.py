from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.schemas.pydantic.category import (
    CategoryBreadcrumbResponse,
    CategoryDetailQueryParams,
    CategoryDetailResponse,
    CategorySeoResponse,
    CategoryListQueryParams,
    CategoryListResponse,
    CategoryShortResponse,
    CategoryTreeQueryParams,
    CategoryTreeResponse,
)
from source.services.category import CategoryService
from source.services.category_cache import CategoryCacheService
from source.utils.query_hash import build_query_hash
from source.utils.slug import normalize_slug, validate_slug


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

    async def delete_by_pattern(self, pattern: str) -> None:
        prefix = pattern.removesuffix("*")
        keys = [key for key in self.values if key.startswith(prefix)]
        for key in keys:
            self.deleted.append(key)
            self.values.pop(key, None)
            self.ttls.pop(key, None)


class FakeCategoryRepository:
    def __init__(self, categories: list[object] | None = None) -> None:
        self.categories = categories if categories is not None else [
            build_category(category_id=2, name="Овощи", slug="ovoshchi", sort_order=20, products_count=95),
            build_category(category_id=1, name="Фрукты", slug="frukty", sort_order=10, products_count=120),
        ]
        self.query: CategoryListQueryParams | None = None
        self.get_active_all_calls = 0
        self.get_active_by_id_calls = 0
        self.get_active_by_slug_calls = 0
        self.get_active_children_calls = 0
        self.get_parent_chain_calls = 0

    async def get_active_list(self, *, session, query: CategoryListQueryParams):
        self.query = query
        categories = self._filter_categories(query=query)
        categories.sort(key=lambda category: (category.sort_order, category.name))
        return [
            build_category_response(category)
            for category in categories[query.offset : query.offset + query.limit]
        ]

    async def count_active(self, *, session, query: CategoryListQueryParams) -> int:
        return len(self._filter_categories(query=query))

    async def get_active_all(self, *, session):
        self.get_active_all_calls += 1
        categories = [
            category
            for category in self.categories
            if category.is_active and not category.is_deleted
        ]
        categories.sort(key=lambda category: (category.sort_order, category.name))
        return [build_category_response(category) for category in categories]

    async def get_active_by_id(self, *, session, category_id: int):
        self.get_active_by_id_calls += 1
        for category in self.categories:
            if category.id == category_id and category.is_active and not category.is_deleted:
                return build_category_detail_response(category)
        return None

    async def get_active_by_slug(self, *, session, slug: str):
        self.get_active_by_slug_calls += 1
        for category in self.categories:
            if category.slug == slug and category.is_active and not category.is_deleted:
                return build_category_detail_response(category)
        return None

    async def get_active_children(self, *, session, parent_id: int):
        self.get_active_children_calls += 1
        categories = [
            category
            for category in self.categories
            if category.parent_id == parent_id and category.is_active and not category.is_deleted
        ]
        categories.sort(key=lambda category: (category.sort_order, category.name))
        return [build_category_response(category) for category in categories]

    async def get_parent_chain(self, *, session, category_id: int):
        self.get_parent_chain_calls += 1
        categories_by_id = {
            category.id: category
            for category in self.categories
            if category.is_active and not category.is_deleted
        }
        breadcrumbs = []
        current_category = categories_by_id.get(category_id)
        while current_category is not None:
            breadcrumbs.append(
                CategoryBreadcrumbResponse(
                    id=current_category.id,
                    name=current_category.name,
                    slug=current_category.slug,
                ),
            )
            current_category = categories_by_id.get(current_category.parent_id)
        return list(reversed(breadcrumbs))

    def _filter_categories(self, *, query: CategoryListQueryParams) -> list[object]:
        categories = [
            category
            for category in self.categories
            if category.is_active and not category.is_deleted
        ]
        if query.parent_id is not None:
            categories = [category for category in categories if category.parent_id == query.parent_id]
        elif query.only_root:
            categories = [category for category in categories if category.parent_id is None]
        if not query.include_empty:
            categories = [category for category in categories if category.products_count > 0]
        return categories


class FakeProductRepository:
    def __init__(self, counts_by_category_id: dict[int, int] | None = None) -> None:
        self.counts_by_category_id = counts_by_category_id or {}
        self.count_calls = 0

    async def count_active_by_category_id(self, *, session, category_id: int) -> int:
        self.count_calls += 1
        return self.counts_by_category_id.get(category_id, 0)


def build_category(
    *,
    category_id: int,
    name: str,
    slug: str,
    parent_id: int | None = None,
    sort_order: int = 0,
    products_count: int = 1,
    is_active: bool = True,
    is_deleted: bool = False,
    description: str | None = "Свежие фрукты",
    meta_title: str | None = "Фрукты купить онлайн",
    meta_description: str | None = "Свежие фрукты с доставкой",
):
    return SimpleNamespace(
        id=category_id,
        name=name,
        slug=slug,
        description=description,
        parent_id=parent_id,
        image_url=f"/media/categories/{slug}.png",
        sort_order=sort_order,
        products_count=products_count,
        is_active=is_active,
        is_deleted=is_deleted,
        meta_title=meta_title,
        meta_description=meta_description,
    )


def build_category_response(category) -> CategoryShortResponse:
    return CategoryShortResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        parent_id=category.parent_id,
        image_url=category.image_url,
        sort_order=category.sort_order,
        products_count=category.products_count,
    )


def build_category_detail_response(category) -> CategoryDetailResponse:
    seo = None
    if category.meta_title is not None or category.meta_description is not None:
        seo = CategorySeoResponse(
            meta_title=category.meta_title,
            meta_description=category.meta_description,
        )
    return CategoryDetailResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        parent_id=category.parent_id,
        image_url=category.image_url,
        sort_order=category.sort_order,
        seo=seo,
    )


async def execute_get_categories(
    *,
    redis_service: FakeRedisService | None = None,
    category_repository: FakeCategoryRepository | None = None,
    query: CategoryListQueryParams | None = None,
) -> CategoryListResponse:
    return await CategoryService().get_categories(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        category_cache_service=CategoryCacheService(),
        category_repository=category_repository or FakeCategoryRepository(),
        query=query or CategoryListQueryParams(),
    )


async def execute_get_category_tree(
    *,
    redis_service: FakeRedisService | None = None,
    category_repository: FakeCategoryRepository | None = None,
    query: CategoryTreeQueryParams | None = None,
) -> CategoryTreeResponse:
    return await CategoryService().get_category_tree(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        category_cache_service=CategoryCacheService(),
        category_repository=category_repository or FakeCategoryRepository(),
        query=query or CategoryTreeQueryParams(),
    )


async def execute_get_category_by_id(
    *,
    redis_service: FakeRedisService | None = None,
    category_repository: FakeCategoryRepository | None = None,
    product_repository: FakeProductRepository | None = None,
    category_id: int = 1,
    query: CategoryDetailQueryParams | None = None,
) -> CategoryDetailResponse:
    return await CategoryService().get_category_by_id(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        category_cache_service=CategoryCacheService(),
        category_repository=category_repository or FakeCategoryRepository(),
        product_repository=product_repository or FakeProductRepository({1: 120}),
        category_id=category_id,
        query=query or CategoryDetailQueryParams(),
    )


async def execute_get_category_by_slug(
    *,
    redis_service: FakeRedisService | None = None,
    category_repository: FakeCategoryRepository | None = None,
    product_repository: FakeProductRepository | None = None,
    slug: str = "frukty",
    query: CategoryDetailQueryParams | None = None,
) -> CategoryDetailResponse:
    return await CategoryService().get_category_by_slug(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        category_cache_service=CategoryCacheService(),
        category_repository=category_repository or FakeCategoryRepository(),
        product_repository=product_repository or FakeProductRepository({1: 120}),
        slug=slug,
        query=query or CategoryDetailQueryParams(),
    )


@pytest.mark.asyncio
async def test_get_categories_from_postgresql_success() -> None:
    response = await execute_get_categories()

    assert response.total == 2
    assert response.limit == 100
    assert response.offset == 0
    assert response.items[0].id == 1
    assert response.items[0].products_count == 120


@pytest.mark.asyncio
async def test_get_categories_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = CategoryListQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = CategoryListResponse(
        items=[
            build_category_response(
                build_category(category_id=1, name="Фрукты", slug="frukty", products_count=120),
            ),
        ],
        total=1,
        limit=100,
        offset=0,
    )
    redis_service.values[f"categories:list:{query_hash}"] = cached_response.model_dump_json()
    category_repository = FakeCategoryRepository(categories=[])

    response = await execute_get_categories(
        redis_service=redis_service,
        category_repository=category_repository,
        query=query,
    )

    assert response.total == 1
    assert category_repository.query is None


@pytest.mark.asyncio
async def test_get_categories_filter_only_root() -> None:
    response = await execute_get_categories(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty", parent_id=None),
                build_category(category_id=2, name="Яблоки", slug="yabloki", parent_id=1),
            ],
        ),
        query=CategoryListQueryParams(only_root=True),
    )

    assert [category.id for category in response.items] == [1]


@pytest.mark.asyncio
async def test_get_categories_filter_by_parent_id() -> None:
    response = await execute_get_categories(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty", parent_id=None),
                build_category(category_id=2, name="Яблоки", slug="yabloki", parent_id=1),
                build_category(category_id=3, name="Огурцы", slug="ogurtsy", parent_id=4),
            ],
        ),
        query=CategoryListQueryParams(parent_id=1),
    )

    assert [category.id for category in response.items] == [2]


@pytest.mark.asyncio
async def test_get_categories_include_empty_false_excludes_empty_categories() -> None:
    response = await execute_get_categories(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty", products_count=120),
                build_category(category_id=2, name="Пустая", slug="empty", products_count=0),
            ],
        ),
    )

    assert [category.id for category in response.items] == [1]
    assert response.total == 1


@pytest.mark.asyncio
async def test_get_categories_sorts_by_sort_order_and_name() -> None:
    response = await execute_get_categories(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Ягоды", slug="yagody", sort_order=20),
                build_category(category_id=2, name="Овощи", slug="ovoshchi", sort_order=10),
                build_category(category_id=3, name="Фрукты", slug="frukty", sort_order=10),
            ],
        ),
    )

    assert [category.id for category in response.items] == [2, 3, 1]


@pytest.mark.asyncio
async def test_get_categories_pagination() -> None:
    response = await execute_get_categories(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="A", slug="a", sort_order=1),
                build_category(category_id=2, name="B", slug="b", sort_order=2),
                build_category(category_id=3, name="C", slug="c", sort_order=3),
            ],
        ),
        query=CategoryListQueryParams(limit=1, offset=1),
    )

    assert response.total == 3
    assert response.limit == 1
    assert response.offset == 1
    assert [category.id for category in response.items] == [2]


def test_get_categories_invalid_query_params() -> None:
    with pytest.raises(ValidationError):
        CategoryListQueryParams(limit=0)


@pytest.mark.asyncio
async def test_get_categories_excludes_inactive_categories() -> None:
    response = await execute_get_categories(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=2, name="Скрытая", slug="hidden", is_active=False),
            ],
        ),
    )

    assert [category.id for category in response.items] == [1]


@pytest.mark.asyncio
async def test_get_categories_excludes_deleted_categories() -> None:
    response = await execute_get_categories(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=2, name="Удалённая", slug="deleted", is_deleted=True),
            ],
        ),
    )

    assert [category.id for category in response.items] == [1]


@pytest.mark.asyncio
async def test_get_categories_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = CategoryListQueryParams(parent_id=1, limit=50)

    await execute_get_categories(redis_service=redis_service, query=query)

    cache_key = f"categories:list:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.categories.cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_category_by_id_from_postgresql_success() -> None:
    response = await execute_get_category_by_id(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty", products_count=120),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1, products_count=25),
            ],
        ),
        product_repository=FakeProductRepository({1: 120}),
    )

    assert response.id == 1
    assert response.description == "Свежие фрукты"
    assert response.products_count == 120
    assert response.seo is not None
    assert response.seo.meta_title == "Фрукты купить онлайн"


@pytest.mark.asyncio
async def test_get_category_by_id_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = CategoryDetailQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = CategoryDetailResponse(
        id=1,
        name="Фрукты",
        slug="frukty",
        description="Свежие фрукты",
        parent_id=None,
        image_url="/media/categories/frukty.png",
        sort_order=10,
        products_count=120,
        children=[],
        breadcrumbs=[],
    )
    redis_service.values[f"categories:detail:1:{query_hash}"] = cached_response.model_dump_json()
    category_repository = FakeCategoryRepository(categories=[])

    response = await execute_get_category_by_id(
        redis_service=redis_service,
        category_repository=category_repository,
        query=query,
    )

    assert response.id == 1
    assert category_repository.get_active_by_id_calls == 0


@pytest.mark.asyncio
async def test_get_category_by_id_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_category_by_id(
            category_repository=FakeCategoryRepository(categories=[]),
            category_id=999,
        )


@pytest.mark.asyncio
async def test_get_category_by_id_inactive_category_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_category_by_id(
            category_repository=FakeCategoryRepository(
                categories=[build_category(category_id=1, name="Скрытая", slug="hidden", is_active=False)],
            ),
        )


@pytest.mark.asyncio
async def test_get_category_by_id_deleted_category_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_category_by_id(
            category_repository=FakeCategoryRepository(
                categories=[build_category(category_id=1, name="Удалённая", slug="deleted", is_deleted=True)],
            ),
        )


@pytest.mark.asyncio
async def test_get_category_by_id_with_children_returns_active_children() -> None:
    response = await execute_get_category_by_id(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1, sort_order=20),
                build_category(category_id=12, name="Абрикосы", slug="abrikosy", parent_id=1, sort_order=10),
                build_category(category_id=13, name="Скрытая", slug="hidden", parent_id=1, is_active=False),
            ],
        ),
    )

    assert response.children is not None
    assert [child.id for child in response.children] == [12, 11]


@pytest.mark.asyncio
async def test_get_category_by_id_with_breadcrumbs_returns_parent_chain() -> None:
    response = await execute_get_category_by_id(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
                build_category(category_id=111, name="Красные", slug="krasnye", parent_id=11),
            ],
        ),
        category_id=111,
        product_repository=FakeProductRepository({111: 5}),
    )

    assert response.breadcrumbs is not None
    assert [breadcrumb.id for breadcrumb in response.breadcrumbs] == [1, 11, 111]


@pytest.mark.asyncio
async def test_get_category_by_id_with_products_count_returns_count() -> None:
    product_repository = FakeProductRepository({1: 120})

    response = await execute_get_category_by_id(product_repository=product_repository)

    assert response.products_count == 120
    assert product_repository.count_calls == 1


@pytest.mark.asyncio
async def test_get_category_by_id_without_optional_parts() -> None:
    category_repository = FakeCategoryRepository()
    product_repository = FakeProductRepository({1: 120})

    response = await execute_get_category_by_id(
        category_repository=category_repository,
        product_repository=product_repository,
        query=CategoryDetailQueryParams(
            with_children=False,
            with_breadcrumbs=False,
            with_products_count=False,
        ),
    )

    assert response.children is None
    assert response.breadcrumbs is None
    assert response.products_count is None
    assert category_repository.get_active_children_calls == 0
    assert category_repository.get_parent_chain_calls == 0
    assert product_repository.count_calls == 0


@pytest.mark.asyncio
async def test_get_category_by_id_response_does_not_include_service_fields() -> None:
    response = await execute_get_category_by_id()

    response_data = response.model_dump()
    assert "is_active" not in response_data
    assert "is_deleted" not in response_data
    assert "deleted_at" not in response_data
    assert "created_date" not in response_data
    assert "updated_date" not in response_data


@pytest.mark.asyncio
async def test_get_category_by_id_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = CategoryDetailQueryParams(with_children=False)

    await execute_get_category_by_id(redis_service=redis_service, query=query)

    cache_key = f"categories:detail:1:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.categories.detail_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_category_by_slug_from_postgresql_success() -> None:
    response = await execute_get_category_by_slug(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty", products_count=120),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1, products_count=25),
            ],
        ),
        product_repository=FakeProductRepository({1: 120}),
    )

    assert response.id == 1
    assert response.slug == "frukty"
    assert response.products_count == 120
    assert response.seo is not None


@pytest.mark.asyncio
async def test_get_category_by_slug_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = CategoryDetailQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = CategoryDetailResponse(
        id=1,
        name="Фрукты",
        slug="frukty",
        description="Свежие фрукты",
        parent_id=None,
        image_url="/media/categories/frukty.png",
        sort_order=10,
        products_count=120,
        children=[],
        breadcrumbs=[],
    )
    redis_service.values[f"categories:slug:frukty:{query_hash}"] = cached_response.model_dump_json()
    category_repository = FakeCategoryRepository(categories=[])

    response = await execute_get_category_by_slug(
        redis_service=redis_service,
        category_repository=category_repository,
        query=query,
    )

    assert response.id == 1
    assert category_repository.get_active_by_slug_calls == 0


@pytest.mark.asyncio
async def test_get_category_by_slug_normalizes_slug() -> None:
    category_repository = FakeCategoryRepository(
        categories=[build_category(category_id=1, name="Фрукты", slug="frukty")],
    )

    response = await execute_get_category_by_slug(
        category_repository=category_repository,
        slug="  FRUKTY  ",
    )

    assert response.slug == "frukty"


def test_get_category_by_slug_invalid_slug() -> None:
    assert validate_slug(normalize_slug("frukty")) is True
    assert validate_slug(normalize_slug("фрукты")) is False
    assert validate_slug(normalize_slug("f")) is False
    assert validate_slug(normalize_slug("bad slug")) is False


@pytest.mark.asyncio
async def test_get_category_by_slug_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_category_by_slug(
            category_repository=FakeCategoryRepository(categories=[]),
            slug="missing",
        )


@pytest.mark.asyncio
async def test_get_category_by_slug_inactive_category_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_category_by_slug(
            category_repository=FakeCategoryRepository(
                categories=[build_category(category_id=1, name="Скрытая", slug="hidden", is_active=False)],
            ),
            slug="hidden",
        )


@pytest.mark.asyncio
async def test_get_category_by_slug_deleted_category_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_category_by_slug(
            category_repository=FakeCategoryRepository(
                categories=[build_category(category_id=1, name="Удалённая", slug="deleted", is_deleted=True)],
            ),
            slug="deleted",
        )


@pytest.mark.asyncio
async def test_get_category_by_slug_with_children_returns_active_children() -> None:
    response = await execute_get_category_by_slug(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
            ],
        ),
    )

    assert response.children is not None
    assert [child.id for child in response.children] == [11]


@pytest.mark.asyncio
async def test_get_category_by_slug_with_breadcrumbs_returns_parent_chain() -> None:
    response = await execute_get_category_by_slug(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
            ],
        ),
        slug="yabloki",
        product_repository=FakeProductRepository({11: 25}),
    )

    assert response.breadcrumbs is not None
    assert [breadcrumb.id for breadcrumb in response.breadcrumbs] == [1, 11]


@pytest.mark.asyncio
async def test_get_category_by_slug_with_products_count_returns_count() -> None:
    product_repository = FakeProductRepository({1: 120})

    response = await execute_get_category_by_slug(product_repository=product_repository)

    assert response.products_count == 120
    assert product_repository.count_calls == 1


@pytest.mark.asyncio
async def test_get_category_by_slug_response_does_not_include_service_fields() -> None:
    response = await execute_get_category_by_slug()

    response_data = response.model_dump()
    assert "is_active" not in response_data
    assert "is_deleted" not in response_data
    assert "deleted_at" not in response_data
    assert "created_date" not in response_data
    assert "updated_date" not in response_data


@pytest.mark.asyncio
async def test_get_category_by_slug_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = CategoryDetailQueryParams(with_children=False)

    await execute_get_category_by_slug(redis_service=redis_service, slug="FRUKTY", query=query)

    cache_key = f"categories:slug:frukty:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.categories.slug_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_category_tree_from_postgresql_success() -> None:
    response = await execute_get_category_tree(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty", parent_id=None, products_count=10),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1, products_count=25),
            ],
        ),
    )

    assert len(response.items) == 1
    assert response.items[0].id == 1
    assert response.items[0].products_count == 10
    assert response.items[0].children[0].id == 11


@pytest.mark.asyncio
async def test_get_category_tree_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    query = CategoryTreeQueryParams()
    query_hash = build_query_hash(query.model_dump())
    cached_response = CategoryTreeResponse(
        items=[
            {
                "id": 1,
                "name": "Фрукты",
                "slug": "frukty",
                "parent_id": None,
                "image_url": "/media/categories/frukty.png",
                "sort_order": 10,
                "products_count": 120,
                "children": [],
            },
        ],
    )
    redis_service.values[f"categories:tree:{query_hash}"] = cached_response.model_dump_json()
    category_repository = FakeCategoryRepository(categories=[])

    response = await execute_get_category_tree(
        redis_service=redis_service,
        category_repository=category_repository,
        query=query,
    )

    assert response.items[0].id == 1
    assert category_repository.get_active_all_calls == 0


@pytest.mark.asyncio
async def test_get_category_tree_builds_tree_by_parent_id() -> None:
    response = await execute_get_category_tree(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
                build_category(category_id=111, name="Красные", slug="krasnye", parent_id=11),
            ],
        ),
    )

    assert response.items[0].id == 1
    assert response.items[0].children[0].id == 11
    assert response.items[0].children[0].children[0].id == 111


@pytest.mark.asyncio
async def test_get_category_tree_with_root_id_returns_subtree() -> None:
    category_repository = FakeCategoryRepository(
        categories=[
            build_category(category_id=1, name="Фрукты", slug="frukty"),
            build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
            build_category(category_id=12, name="Груши", slug="grushi", parent_id=1),
        ],
    )

    response = await execute_get_category_tree(
        category_repository=category_repository,
        query=CategoryTreeQueryParams(root_id=11),
    )

    assert [category.id for category in response.items] == [11]
    assert category_repository.get_active_by_id_calls == 1


@pytest.mark.asyncio
async def test_get_category_tree_root_id_not_found() -> None:
    with pytest.raises(CategoryNotFoundError):
        await execute_get_category_tree(
            category_repository=FakeCategoryRepository(categories=[]),
            query=CategoryTreeQueryParams(root_id=999),
        )


@pytest.mark.asyncio
async def test_get_category_tree_max_depth_limits_children() -> None:
    response = await execute_get_category_tree(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
                build_category(category_id=111, name="Красные", slug="krasnye", parent_id=11),
            ],
        ),
        query=CategoryTreeQueryParams(max_depth=2),
    )

    assert response.items[0].children[0].id == 11
    assert response.items[0].children[0].children == []


@pytest.mark.asyncio
async def test_get_category_tree_include_empty_false_excludes_empty_branches() -> None:
    response = await execute_get_category_tree(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty", products_count=0),
                build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1, products_count=12),
                build_category(category_id=2, name="Пустая", slug="empty", products_count=0),
            ],
        ),
    )

    assert [category.id for category in response.items] == [1]
    assert response.items[0].children[0].id == 11


@pytest.mark.asyncio
async def test_get_category_tree_sorts_each_level_by_sort_order_and_name() -> None:
    response = await execute_get_category_tree(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty", sort_order=20),
                build_category(category_id=2, name="Овощи", slug="ovoshchi", sort_order=10),
                build_category(category_id=21, name="Томаты", slug="tomaty", parent_id=2, sort_order=20),
                build_category(category_id=22, name="Огурцы", slug="ogurtsy", parent_id=2, sort_order=10),
            ],
        ),
    )

    assert [category.id for category in response.items] == [2, 1]
    assert [category.id for category in response.items[0].children] == [22, 21]


@pytest.mark.asyncio
async def test_get_category_tree_excludes_inactive_categories() -> None:
    response = await execute_get_category_tree(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=2, name="Скрытая", slug="hidden", is_active=False),
            ],
        ),
    )

    assert [category.id for category in response.items] == [1]


@pytest.mark.asyncio
async def test_get_category_tree_excludes_deleted_categories() -> None:
    response = await execute_get_category_tree(
        category_repository=FakeCategoryRepository(
            categories=[
                build_category(category_id=1, name="Фрукты", slug="frukty"),
                build_category(category_id=2, name="Удалённая", slug="deleted", is_deleted=True),
            ],
        ),
    )

    assert [category.id for category in response.items] == [1]


@pytest.mark.asyncio
async def test_get_category_tree_without_products_count() -> None:
    response = await execute_get_category_tree(
        query=CategoryTreeQueryParams(with_products_count=False),
    )

    assert response.items[0].products_count is None


@pytest.mark.asyncio
async def test_get_category_tree_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()
    query = CategoryTreeQueryParams(root_id=1, max_depth=2)

    await execute_get_category_tree(redis_service=redis_service, query=query)

    cache_key = f"categories:tree:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.categories.tree_cache_ttl_seconds


@pytest.mark.asyncio
async def test_get_category_tree_uses_single_active_all_query_without_n_plus_one() -> None:
    category_repository = FakeCategoryRepository(
        categories=[
            build_category(category_id=1, name="Фрукты", slug="frukty"),
            build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1),
            build_category(category_id=12, name="Груши", slug="grushi", parent_id=1),
        ],
    )

    await execute_get_category_tree(category_repository=category_repository)

    assert category_repository.get_active_all_calls == 1
