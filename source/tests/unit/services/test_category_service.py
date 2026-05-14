from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.schemas.pydantic.category import CategoryListQueryParams, CategoryListResponse, CategoryShortResponse
from source.services.category import CategoryService
from source.services.category_cache import CategoryCacheService
from source.utils.query_hash import build_query_hash


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
):
    return SimpleNamespace(
        id=category_id,
        name=name,
        slug=slug,
        parent_id=parent_id,
        image_url=f"/media/categories/{slug}.png",
        sort_order=sort_order,
        products_count=products_count,
        is_active=is_active,
        is_deleted=is_deleted,
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
