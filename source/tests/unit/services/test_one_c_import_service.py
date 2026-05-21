from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.integration import import_one_c_categories
from source.api.dependencies import verify_one_c_token
from source.config.settings import settings
from source.schemas.pydantic.one_c import OneCCategoryImportItem, OneCCategoryImportRequest
from source.services.admin_category_cache import AdminCategoryCacheService
from source.services.category_cache import CategoryCacheService
from source.services.one_c import CategorySyncService, IntegrationLogService, OneCImportService
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


def build_request(*items) -> OneCCategoryImportRequest:
    return OneCCategoryImportRequest(items=list(items))


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
