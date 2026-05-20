from datetime import datetime
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.category import CategoryNotFoundError, CategorySlugAlreadyExistsError
from source.errors.upload import UploadNotFoundError
from source.schemas.pydantic.admin_category import (
    AdminCategoryCreateRequest,
    AdminCategoryListQueryParams,
    AdminCategoryListResponse,
)
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_category import AdminCategoryService
from source.services.admin_category_cache import AdminCategoryCacheService
from source.services.category_cache import CategoryCacheService
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


class FakeCategoryRepository:
    def __init__(self, *, categories: list[SimpleNamespace]) -> None:
        self.categories = categories
        self.called = False

    async def admin_get_list(self, *, session, query: AdminCategoryListQueryParams):
        self.called = True
        categories = self._filter(query=query)
        categories = sorted(categories, key=lambda category: (category.sort_order, category.name))
        return categories[query.offset : query.offset + query.limit]

    async def admin_count(self, *, session, query: AdminCategoryListQueryParams):
        return len(self._filter(query=query))

    async def get_by_slug(self, *, session, slug: str):
        return next((category for category in self.categories if category.slug == slug), None)

    async def get_by_id(self, *, session, category_id: int):
        return next(
            (
                category
                for category in self.categories
                if category.id == category_id and not category.is_deleted
            ),
            None,
        )

    async def create(self, *, session, data: AdminCategoryCreateRequest, slug: str, image_url: str | None):
        category = SimpleNamespace(
            id=100,
            name=data.name,
            slug=slug,
            description=data.description,
            parent_id=data.parent_id,
            image_file_id=data.image_id,
            image_url=image_url,
            sort_order=data.sort_order,
            is_active=data.is_active,
            is_deleted=False,
            created_date=datetime(2026, 5, 12, 10),
        )
        self.categories.append(category)
        return category

    def _filter(self, *, query: AdminCategoryListQueryParams):
        categories = list(self.categories)
        if not query.include_deleted:
            categories = [category for category in categories if not category.is_deleted]
        if query.q is not None:
            q = query.q.lower()
            categories = [
                category
                for category in categories
                if q in category.name.lower() or q in category.slug.lower()
            ]
        if query.parent_id is not None:
            categories = [category for category in categories if category.parent_id == query.parent_id]
        if query.is_active is not None:
            categories = [category for category in categories if category.is_active is query.is_active]
        return categories


class FakeProductRepository:
    def __init__(self, *, counts_by_category_id: dict[int, int] | None = None) -> None:
        self.counts_by_category_id = counts_by_category_id or {}

    async def count_by_category_id(self, *, session, category_id: int) -> int:
        return self.counts_by_category_id.get(category_id, 0)


class FakeUploadRepository:
    def __init__(self, *, uploads: list[SimpleNamespace] | None = None) -> None:
        self.uploads = uploads if uploads is not None else [
            SimpleNamespace(id=1001, url="/media/categories/fruits.png", is_deleted=False),
        ]

    async def get_by_id(self, *, session, file_id: int):
        return next((upload for upload in self.uploads if upload.id == file_id), None)


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(id=1, **data)


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


def build_user(*, role=UserRole.ADMIN, is_active: bool = True, is_deleted: bool = False):
    return SimpleNamespace(
        id=1,
        role=role,
        is_active=is_active,
        is_deleted=is_deleted,
        email="admin@example.com",
        phone="+79990000000",
    )


def build_category(
    *,
    category_id: int,
    name: str,
    slug: str,
    parent_id: int | None = None,
    sort_order: int = 10,
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
        is_active=is_active,
        is_deleted=is_deleted,
        created_date=datetime(2026, 5, 12, 10),
    )


def build_category_repository() -> FakeCategoryRepository:
    return FakeCategoryRepository(
        categories=[
            build_category(category_id=1, name="Фрукты", slug="frukty", sort_order=10),
            build_category(category_id=2, name="Овощи", slug="ovoshchi", sort_order=20),
            build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1, sort_order=10),
            build_category(category_id=12, name="Груши", slug="grushi", parent_id=1, sort_order=20, is_active=False),
            build_category(category_id=99, name="Удалённая", slug="deleted", is_deleted=True),
        ],
    )


async def get_categories(
    *,
    redis_service=None,
    user=None,
    category_repository=None,
    product_repository=None,
    query=None,
):
    return await AdminCategoryService().get_categories(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        query=query or AdminCategoryListQueryParams(),
        permission_service=PermissionService(),
        category_repository=category_repository or build_category_repository(),
        product_repository=product_repository
        or FakeProductRepository(counts_by_category_id={1: 120, 2: 95, 11: 25, 12: 10, 99: 3}),
        admin_category_cache_service=AdminCategoryCacheService(),
    )


async def create_category(
    *,
    redis_service=None,
    user=None,
    category_repository=None,
    upload_repository=None,
    audit_log_repository=None,
    commiter=None,
    data=None,
):
    return await AdminCategoryService().create_category(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        data=data
        or AdminCategoryCreateRequest(
            name="Фрукты",
            slug="frukty-new",
            description="Свежие фрукты",
            parent_id=None,
            image_id=1001,
            sort_order=10,
            is_active=True,
            meta_title="Фрукты купить онлайн",
            meta_description="Свежие фрукты с доставкой",
        ),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        category_repository=category_repository or build_category_repository(),
        upload_repository=upload_repository or FakeUploadRepository(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        audit_log_service=AuditLogService(),
        category_cache_service=CategoryCacheService(),
        admin_category_cache_service=AdminCategoryCacheService(),
    )


@pytest.mark.asyncio
async def test_admin_categories_list_success() -> None:
    response = await get_categories()

    assert response.total == 4
    assert response.page == 1
    assert response.limit == 50
    assert [item.name for item in response.items] == ["Фрукты", "Яблоки", "Груши", "Овощи"]
    assert response.items[0].products_count == 120


@pytest.mark.asyncio
async def test_admin_categories_filter_q() -> None:
    response = await get_categories(query=AdminCategoryListQueryParams(q="  frukty  "))

    assert response.total == 1
    assert response.items[0].name == "Фрукты"


@pytest.mark.asyncio
async def test_admin_categories_filter_parent_id() -> None:
    response = await get_categories(query=AdminCategoryListQueryParams(parent_id=1))

    assert response.total == 2
    assert [item.name for item in response.items] == ["Яблоки", "Груши"]


@pytest.mark.asyncio
async def test_admin_categories_filter_is_active() -> None:
    response = await get_categories(query=AdminCategoryListQueryParams(is_active=False))

    assert response.total == 1
    assert response.items[0].name == "Груши"


@pytest.mark.asyncio
async def test_admin_categories_include_deleted_false_hides_deleted() -> None:
    response = await get_categories(query=AdminCategoryListQueryParams())

    assert all(not item.is_deleted for item in response.items)
    assert "Удалённая" not in [item.name for item in response.items]


@pytest.mark.asyncio
async def test_admin_categories_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_categories(user=build_user(role=UserRole.PICKER))


@pytest.mark.asyncio
async def test_admin_categories_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    query = AdminCategoryListQueryParams(q="Фрукты")
    cached_response = AdminCategoryListResponse(items=[], total=0, page=1, limit=50, pages=0)
    normalized_query = query.model_copy(update={"q": normalize_search_query(query.q)})
    query_hash = build_query_hash(normalized_query.model_dump())
    redis_service.values[f"admin:categories:list:{query_hash}"] = cached_response.model_dump_json()
    category_repository = build_category_repository()

    response = await get_categories(
        redis_service=redis_service,
        category_repository=category_repository,
        query=query,
    )

    assert response == cached_response
    assert category_repository.called is False


@pytest.mark.asyncio
async def test_admin_categories_response_is_cached() -> None:
    redis_service = FakeRedisService()
    query = AdminCategoryListQueryParams(parent_id=1)

    await get_categories(redis_service=redis_service, query=query)

    cache_key = f"admin:categories:list:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.categories.admin_list_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_category_create_success() -> None:
    commiter = FakeCommiter()

    response = await create_category(commiter=commiter)

    assert response.id == 100
    assert response.name == "Фрукты"
    assert response.slug == "frukty-new"
    assert response.description == "Свежие фрукты"
    assert response.image_url == "/media/categories/fruits.png"
    assert response.sort_order == 10
    assert response.is_active is True
    assert commiter.committed is True


@pytest.mark.asyncio
async def test_admin_category_create_slug_generated_from_name() -> None:
    response = await create_category(data=AdminCategoryCreateRequest(name="Свежие фрукты"))

    assert response.slug == "svezhie-frukty"


@pytest.mark.asyncio
async def test_admin_category_create_slug_taken_error() -> None:
    with pytest.raises(CategorySlugAlreadyExistsError):
        await create_category(data=AdminCategoryCreateRequest(name="Фрукты", slug="frukty"))


@pytest.mark.asyncio
async def test_admin_category_create_parent_not_found_error() -> None:
    with pytest.raises(CategoryNotFoundError):
        await create_category(data=AdminCategoryCreateRequest(name="Бананы", slug="banany", parent_id=999))


@pytest.mark.asyncio
async def test_admin_category_create_deleted_parent_not_found_error() -> None:
    with pytest.raises(CategoryNotFoundError):
        await create_category(data=AdminCategoryCreateRequest(name="Бананы", slug="banany", parent_id=99))


@pytest.mark.asyncio
async def test_admin_category_create_image_not_found_error() -> None:
    with pytest.raises(UploadNotFoundError):
        await create_category(
            data=AdminCategoryCreateRequest(name="Бананы", slug="banany", image_id=999),
        )


@pytest.mark.asyncio
async def test_admin_category_create_deleted_image_not_found_error() -> None:
    with pytest.raises(UploadNotFoundError):
        await create_category(
            data=AdminCategoryCreateRequest(name="Бананы", slug="banany", image_id=1001),
            upload_repository=FakeUploadRepository(
                uploads=[SimpleNamespace(id=1001, url="/media/categories/old.png", is_deleted=True)],
            ),
        )


@pytest.mark.asyncio
async def test_admin_category_create_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await create_category(user=build_user(role=UserRole.PICKER))


@pytest.mark.asyncio
async def test_admin_category_create_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await create_category(redis_service=redis_service)

    assert "admin:categories:*" in redis_service.deleted_patterns
    assert "categories:list:*" in redis_service.deleted_patterns
    assert "categories:tree:*" in redis_service.deleted_patterns
    assert "categories:detail:*" in redis_service.deleted_patterns
    assert "categories:slug:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_category_create_audit_log_created() -> None:
    audit_log_repository = FakeAuditLogRepository()

    await create_category(audit_log_repository=audit_log_repository)

    assert len(audit_log_repository.logs) == 1
    assert audit_log_repository.logs[0]["event"] == "admin_category_create"
    assert audit_log_repository.logs[0]["status"] == "success"
    assert audit_log_repository.logs[0]["details"]["category_id"] == 100
