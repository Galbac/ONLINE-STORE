from datetime import datetime
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.category import CategoryCycleError, CategoryNotFoundError, CategorySlugAlreadyExistsError
from source.errors.upload import UploadNotFoundError
from source.schemas.pydantic.admin_category import (
    AdminCategoryCreateRequest,
    AdminCategoryDetailResponse,
    AdminCategoryListQueryParams,
    AdminCategoryListResponse,
    AdminCategoryUpdateRequest,
)
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_category import AdminCategoryService, CategoryTreeService
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

    async def admin_get_by_id(self, *, session, category_id: int):
        self.called = True
        return next(
            (
                category
                for category in self.categories
                if category.id == category_id and not category.is_deleted
            ),
            None,
        )

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

    async def get_children(self, *, session, parent_id: int):
        return sorted(
            [
                category
                for category in self.categories
                if category.parent_id == parent_id and not category.is_deleted
            ],
            key=lambda category: (category.sort_order, category.name),
        )

    async def get_descendant_ids(self, *, session, category_id: int):
        children_by_parent_id = {}
        for category in self.categories:
            if not category.is_deleted:
                children_by_parent_id.setdefault(category.parent_id, []).append(category.id)
        descendant_ids = set()
        pending_ids = list(children_by_parent_id.get(category_id, []))
        while pending_ids:
            current_id = pending_ids.pop()
            if current_id in descendant_ids:
                continue
            descendant_ids.add(current_id)
            pending_ids.extend(children_by_parent_id.get(current_id, []))
        return descendant_ids

    async def update(self, *, session, category, data: dict):
        for field, value in data.items():
            setattr(category, field, value)
        category.updated_date = datetime(2026, 5, 12, 11)
        return category

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
        description=f"{name} описание",
        parent_id=parent_id,
        image_file_id=1001 if category_id == 1 else None,
        image_url=f"/media/categories/{slug}.png",
        sort_order=sort_order,
        is_active=is_active,
        is_deleted=is_deleted,
        meta_title=f"{name} купить онлайн",
        meta_description=f"{name} с доставкой",
        created_date=datetime(2026, 5, 12, 10),
        updated_date=datetime(2026, 5, 12, 10),
    )


def build_category_repository() -> FakeCategoryRepository:
    return FakeCategoryRepository(
        categories=[
            build_category(category_id=1, name="Фрукты", slug="frukty", sort_order=10),
            build_category(category_id=2, name="Овощи", slug="ovoshchi", sort_order=20),
            build_category(category_id=11, name="Яблоки", slug="yabloki", parent_id=1, sort_order=10),
            build_category(category_id=111, name="Красные яблоки", slug="krasnye-yabloki", parent_id=11, sort_order=10),
            build_category(category_id=12, name="Груши", slug="grushi", parent_id=1, sort_order=20, is_active=False),
            build_category(category_id=99, name="Удалённая", slug="deleted", is_deleted=True),
        ],
    )


class FakeProductCacheService:
    async def invalidate_all(self, *, redis_service: FakeRedisService) -> None:
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:detail:*")
        await redis_service.delete_by_pattern("products:slug:*")


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
        or FakeProductRepository(counts_by_category_id={1: 120, 2: 95, 11: 25, 111: 8, 12: 10, 99: 3}),
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


async def get_category_detail(
    *,
    redis_service=None,
    user=None,
    category_repository=None,
    product_repository=None,
    upload_repository=None,
    category_id: int = 1,
):
    return await AdminCategoryService().get_category_detail(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        category_id=category_id,
        permission_service=PermissionService(),
        category_repository=category_repository or build_category_repository(),
        product_repository=product_repository
        or FakeProductRepository(counts_by_category_id={1: 120, 2: 95, 11: 25, 111: 8, 12: 10, 99: 3}),
        upload_repository=upload_repository or FakeUploadRepository(),
        admin_category_cache_service=AdminCategoryCacheService(),
    )


async def update_category(
    *,
    redis_service=None,
    user=None,
    category_repository=None,
    upload_repository=None,
    audit_log_repository=None,
    commiter=None,
    data=None,
    category_id: int = 1,
):
    return await AdminCategoryService().update_category(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=user or build_user(),
        category_id=category_id,
        data=data
        or AdminCategoryUpdateRequest(
            name="Фрукты и ягоды",
            slug="frukty-i-yagody",
            description="Свежие фрукты и ягоды",
            parent_id=None,
            image_id=1001,
            sort_order=20,
            is_active=True,
            meta_title="Фрукты и ягоды купить",
            meta_description="Фрукты и ягоды с доставкой",
        ),
        commiter=commiter or FakeCommiter(),
        permission_service=PermissionService(),
        category_repository=category_repository or build_category_repository(),
        upload_repository=upload_repository or FakeUploadRepository(),
        admin_audit_log_repository=audit_log_repository or FakeAuditLogRepository(),
        audit_log_service=AuditLogService(),
        category_tree_service=CategoryTreeService(),
        category_cache_service=CategoryCacheService(),
        admin_category_cache_service=AdminCategoryCacheService(),
        product_cache_service=FakeProductCacheService(),
    )


@pytest.mark.asyncio
async def test_admin_categories_list_success() -> None:
    response = await get_categories()

    assert response.total == 5
    assert response.page == 1
    assert response.limit == 50
    assert [item.name for item in response.items] == ["Красные яблоки", "Фрукты", "Яблоки", "Груши", "Овощи"]
    assert response.items[1].products_count == 120


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
async def test_admin_category_detail_success() -> None:
    response = await get_category_detail()

    assert response.id == 1
    assert response.name == "Фрукты"
    assert response.slug == "frukty"
    assert response.parent is None
    assert [child.id for child in response.children] == [11, 12]
    assert response.image.id == 1001
    assert response.image.url == "/media/categories/fruits.png"
    assert response.products_count == 120
    assert response.seo.meta_title == "Фрукты купить онлайн"
    assert response.seo.meta_description == "Фрукты с доставкой"


@pytest.mark.asyncio
async def test_admin_category_detail_with_parent_success() -> None:
    response = await get_category_detail(category_id=11)

    assert response.id == 11
    assert response.parent.id == 1
    assert response.parent.name == "Фрукты"
    assert [child.id for child in response.children] == [111]


@pytest.mark.asyncio
async def test_admin_category_detail_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminCategoryDetailResponse(
        id=1,
        name="Фрукты",
        slug="frukty",
        sort_order=10,
        is_active=True,
        products_count=120,
        children=[],
    )
    redis_service.values["admin:categories:detail:1"] = cached_response.model_dump_json()
    category_repository = build_category_repository()

    response = await get_category_detail(
        redis_service=redis_service,
        category_repository=category_repository,
    )

    assert response == cached_response
    assert category_repository.called is False


@pytest.mark.asyncio
async def test_admin_category_detail_not_found_error() -> None:
    with pytest.raises(CategoryNotFoundError):
        await get_category_detail(category_id=999)


@pytest.mark.asyncio
async def test_admin_category_detail_deleted_category_not_returned() -> None:
    with pytest.raises(CategoryNotFoundError):
        await get_category_detail(category_id=99)


@pytest.mark.asyncio
async def test_admin_category_detail_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_category_detail(user=build_user(role=UserRole.PICKER))


@pytest.mark.asyncio
async def test_admin_category_detail_response_is_cached() -> None:
    redis_service = FakeRedisService()

    await get_category_detail(redis_service=redis_service)

    assert "admin:categories:detail:1" in redis_service.values
    assert redis_service.ttls["admin:categories:detail:1"] == settings.categories.admin_list_cache_ttl_seconds


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


@pytest.mark.asyncio
async def test_admin_category_update_success() -> None:
    commiter = FakeCommiter()

    response = await update_category(commiter=commiter)

    assert response.id == 1
    assert response.name == "Фрукты и ягоды"
    assert response.slug == "frukty-i-yagody"
    assert response.parent_id is None
    assert response.sort_order == 20
    assert response.is_active is True
    assert response.updated_at == datetime(2026, 5, 12, 11)
    assert commiter.committed is True


@pytest.mark.asyncio
async def test_admin_category_update_no_fields_error() -> None:
    with pytest.raises(ValueError, match="No fields to update"):
        await update_category(data=AdminCategoryUpdateRequest())


@pytest.mark.asyncio
async def test_admin_category_update_slug_taken_error() -> None:
    with pytest.raises(CategorySlugAlreadyExistsError):
        await update_category(data=AdminCategoryUpdateRequest(slug="ovoshchi"))


@pytest.mark.asyncio
async def test_admin_category_update_parent_not_found_error() -> None:
    with pytest.raises(CategoryNotFoundError):
        await update_category(data=AdminCategoryUpdateRequest(parent_id=999))


@pytest.mark.asyncio
async def test_admin_category_update_parent_self_cycle_error() -> None:
    with pytest.raises(CategoryCycleError):
        await update_category(data=AdminCategoryUpdateRequest(parent_id=1))


@pytest.mark.asyncio
async def test_admin_category_update_descendant_cycle_error() -> None:
    with pytest.raises(CategoryCycleError):
        await update_category(data=AdminCategoryUpdateRequest(parent_id=111))


@pytest.mark.asyncio
async def test_admin_category_update_image_not_found_error() -> None:
    with pytest.raises(UploadNotFoundError):
        await update_category(data=AdminCategoryUpdateRequest(image_id=999))


@pytest.mark.asyncio
async def test_admin_category_update_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await update_category(user=build_user(role=UserRole.PICKER))


@pytest.mark.asyncio
async def test_admin_category_update_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await update_category(redis_service=redis_service)

    assert "admin:categories:*" in redis_service.deleted_patterns
    assert "categories:list:*" in redis_service.deleted_patterns
    assert "categories:tree:*" in redis_service.deleted_patterns
    assert "categories:detail:1:*" in redis_service.deleted_patterns
    assert "categories:slug:frukty:*" in redis_service.deleted_patterns
    assert "categories:slug:frukty-i-yagody:*" in redis_service.deleted_patterns
    assert "products:list:*" in redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_category_update_audit_log_created() -> None:
    audit_log_repository = FakeAuditLogRepository()

    await update_category(audit_log_repository=audit_log_repository)

    assert len(audit_log_repository.logs) == 1
    assert audit_log_repository.logs[0]["event"] == "admin_category_update"
    assert audit_log_repository.logs[0]["status"] == "success"
    assert audit_log_repository.logs[0]["details"]["category_id"] == 1
    assert audit_log_repository.logs[0]["details"]["changes"]["name"] == {
        "old": "Фрукты",
        "new": "Фрукты и ягоды",
    }
