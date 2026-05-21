from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.category import CategoryNotFoundError
from source.errors.product import ProductNotFoundError
from source.schemas.pydantic.discount import AdminDiscountCreateRequest, AdminDiscountListQueryParams, AdminDiscountListResponse
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_discount import AdminDiscountService, DiscountConflictService
from source.services.admin_discount_cache import AdminDiscountCacheService
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


class FakeDiscountRepository:
    def __init__(self, discounts=None) -> None:
        self.discounts = discounts if discounts is not None else [
            build_discount(discount_id=1, name="Скидка на яблоки", type="product", is_active=True),
            build_discount(discount_id=2, name="Скидка на овощи", type="category", is_active=False),
            build_discount(discount_id=3, name="Корзина", type="cart", is_active=True),
        ]
        self.list_calls = 0
        self.count_calls = 0

    async def admin_get_list(self, *, session, query: AdminDiscountListQueryParams):
        self.list_calls += 1
        discounts = self._filter(query=query)
        discounts.sort(key=lambda discount: discount.created_date, reverse=True)
        return discounts[query.offset : query.offset + query.limit]

    async def admin_count(self, *, session, query: AdminDiscountListQueryParams) -> int:
        self.count_calls += 1
        return len(self._filter(query=query))

    async def create(self, *, session, **data):
        discount = build_discount(discount_id=len(self.discounts) + 1, **data)
        self.discounts.append(discount)
        return discount

    def _filter(self, *, query: AdminDiscountListQueryParams):
        discounts = [discount for discount in self.discounts if not discount.is_deleted]
        if query.q is not None:
            q = query.q.lower()
            discounts = [discount for discount in discounts if q in discount.name.lower()]
        if query.type is not None:
            discounts = [discount for discount in discounts if discount.type == query.type]
        if query.discount_type is not None:
            discounts = [discount for discount in discounts if discount.discount_type == query.discount_type]
        if query.is_active is not None:
            discounts = [discount for discount in discounts if discount.is_active is query.is_active]
        if query.date_from is not None:
            discounts = [discount for discount in discounts if discount.created_date.date() >= query.date_from]
        if query.date_to is not None:
            discounts = [discount for discount in discounts if discount.created_date.date() <= query.date_to]
        return discounts


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(
        id=1,
        role=role,
        is_active=True,
        is_deleted=False,
        is_blocked=False,
        email="admin@example.com",
        phone="+79998887766",
    )


def build_discount(
    *,
    discount_id: int,
    name: str,
    type: str = "product",
    discount_type: str = "percent",
    is_active: bool = True,
    created_date=None,
    **extra,
):
    created_date = created_date or datetime(2026, 5, 12, 10, 0, 0) + timedelta(minutes=discount_id)
    return SimpleNamespace(
        id=discount_id,
        name=name,
        type=type,
        discount_type=discount_type,
        discount_value=Decimal("20"),
        is_active=is_active,
        is_deleted=False,
        starts_at=datetime(2026, 5, 1, 0, 0, 0),
        ends_at=datetime(2026, 5, 31, 23, 59, 59),
        created_date=created_date,
        applicable_product_id=extra.get("applicable_product_id"),
        applicable_category_id=extra.get("applicable_category_id"),
    )


class FakeDiscountProductRepository:
    def __init__(self) -> None:
        self.created = []

    async def bulk_create(self, *, session, discount_id: int, product_ids: list[int]):
        self.created.append((discount_id, product_ids))
        return []


class FakeDiscountCategoryRepository:
    def __init__(self) -> None:
        self.created = []

    async def bulk_create(self, *, session, discount_id: int, category_ids: list[int]):
        self.created.append((discount_id, category_ids))
        return []


class FakeProductRepository:
    def __init__(self, product_ids=None) -> None:
        self.product_ids = product_ids if product_ids is not None else [55]

    async def get_by_ids(self, *, session, product_ids: list[int]):
        return [SimpleNamespace(id=product_id) for product_id in product_ids if product_id in self.product_ids]


class FakeCategoryRepository:
    def __init__(self, category_ids=None) -> None:
        self.category_ids = category_ids if category_ids is not None else [2]

    async def get_by_ids(self, *, session, category_ids: list[int]):
        return [SimpleNamespace(id=category_id) for category_id in category_ids if category_id in self.category_ids]


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def create(self, *, session, **data):
        self.logs.append(data)
        return SimpleNamespace(**data)


async def get_discounts(*, query=None, redis_service=None, role=UserRole.ADMIN, repository=None):
    return await AdminDiscountService().get_discounts(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_user(role=role),
        query=query or AdminDiscountListQueryParams(),
        permission_service=PermissionService(),
        discount_repository=repository or FakeDiscountRepository(),
        admin_discount_cache_service=AdminDiscountCacheService(),
    )


async def create_discount(
    *,
    data: AdminDiscountCreateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    discount_repository=None,
    discount_product_repository=None,
    discount_category_repository=None,
    product_repository=None,
    category_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    discount_product_repository = discount_product_repository or FakeDiscountProductRepository()
    discount_category_repository = discount_category_repository or FakeDiscountCategoryRepository()
    response = await AdminDiscountService().create_discount(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        data=data or AdminDiscountCreateRequest(
            name="Скидка на яблоки",
            type="product",
            product_ids=[55],
            discount_type="percent",
            discount_value=Decimal("20"),
            starts_at=datetime(2026, 5, 1, 0, 0, 0),
            ends_at=datetime(2026, 5, 31, 23, 59, 59),
            is_active=True,
        ),
        commiter=commiter,
        permission_service=PermissionService(),
        discount_repository=discount_repository or FakeDiscountRepository(discounts=[]),
        discount_product_repository=discount_product_repository,
        discount_category_repository=discount_category_repository,
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        discount_conflict_service=DiscountConflictService(),
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
        admin_discount_cache_service=AdminDiscountCacheService(),
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
        discount_product_repository=discount_product_repository,
        discount_category_repository=discount_category_repository,
    )


@pytest.mark.asyncio
async def test_admin_get_discounts_success() -> None:
    response = await get_discounts()

    assert response.total == 3
    assert response.page == 1
    assert response.limit == 50
    assert response.pages == 1
    assert response.items[0].id == 3


@pytest.mark.asyncio
async def test_admin_get_discounts_filters_by_type() -> None:
    response = await get_discounts(query=AdminDiscountListQueryParams(type="category"))

    assert response.total == 1
    assert response.items[0].type == "category"


@pytest.mark.asyncio
async def test_admin_get_discounts_filters_by_is_active() -> None:
    response = await get_discounts(query=AdminDiscountListQueryParams(is_active=False))

    assert response.total == 1
    assert response.items[0].is_active is False


@pytest.mark.asyncio
async def test_admin_get_discounts_searches_by_q() -> None:
    response = await get_discounts(query=AdminDiscountListQueryParams(q="  яблоки  "))

    assert response.total == 1
    assert response.items[0].name == "Скидка на яблоки"


@pytest.mark.asyncio
async def test_admin_get_discounts_pagination() -> None:
    response = await get_discounts(query=AdminDiscountListQueryParams(page=2, limit=2))

    assert response.total == 3
    assert response.pages == 2
    assert len(response.items) == 1
    assert response.items[0].id == 1


@pytest.mark.asyncio
async def test_admin_get_discounts_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_discounts(role=UserRole.MANAGER)


@pytest.mark.asyncio
async def test_admin_get_discounts_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    query = AdminDiscountListQueryParams(q="Яблоки")
    normalized_query = query.model_copy(update={"q": normalize_search_query(query.q)})
    cached_response = AdminDiscountListResponse.build(items=[], total=0, page=query.page, limit=query.limit)
    redis_service.values[
        f"admin:discounts:list:{build_query_hash(normalized_query.model_dump())}"
    ] = cached_response.model_dump_json()
    repository = FakeDiscountRepository()

    response = await get_discounts(redis_service=redis_service, repository=repository, query=query)

    assert response == cached_response
    assert repository.list_calls == 0
    assert repository.count_calls == 0


@pytest.mark.asyncio
async def test_admin_get_discounts_response_is_cached() -> None:
    redis_service = FakeRedisService()
    query = AdminDiscountListQueryParams(type="product")

    await get_discounts(redis_service=redis_service, query=query)

    cache_key = f"admin:discounts:list:{build_query_hash(query.model_dump())}"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.discounts.admin_list_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_create_product_discount_success() -> None:
    result = await create_discount()

    assert result.response.name == "Скидка на яблоки"
    assert result.response.type == "product"
    assert result.response.discount_type == "percent"
    assert result.response.discount_value == Decimal("20")
    assert result.response.is_active is True
    assert result.discount_product_repository.created == [(1, [55])]
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_create_category_discount_success() -> None:
    category_repository = FakeDiscountCategoryRepository()

    result = await create_discount(
        data=AdminDiscountCreateRequest(
            name="Скидка на овощи",
            type="category",
            category_ids=[2],
            discount_type="percent",
            discount_value=Decimal("10"),
            starts_at=datetime(2026, 5, 1, 0, 0, 0),
            ends_at=datetime(2026, 5, 31, 23, 59, 59),
            is_active=True,
        ),
        discount_category_repository=category_repository,
    )

    assert result.response.type == "category"
    assert category_repository.created == [(1, [2])]


def test_admin_create_discount_percent_above_100_error() -> None:
    with pytest.raises(ValidationError):
        AdminDiscountCreateRequest(
            name="Скидка",
            type="product",
            product_ids=[55],
            discount_type="percent",
            discount_value=Decimal("101"),
        )


@pytest.mark.asyncio
async def test_admin_create_discount_product_not_found_error() -> None:
    with pytest.raises(ProductNotFoundError):
        await create_discount(product_repository=FakeProductRepository(product_ids=[]))


@pytest.mark.asyncio
async def test_admin_create_discount_category_not_found_error() -> None:
    with pytest.raises(CategoryNotFoundError):
        await create_discount(
            data=AdminDiscountCreateRequest(
                name="Скидка на овощи",
                type="category",
                category_ids=[2],
                discount_type="percent",
                discount_value=Decimal("10"),
            ),
            category_repository=FakeCategoryRepository(category_ids=[]),
        )


def test_admin_create_discount_starts_after_ends_error() -> None:
    with pytest.raises(ValidationError):
        AdminDiscountCreateRequest(
            name="Скидка",
            type="product",
            product_ids=[55],
            discount_type="percent",
            discount_value=Decimal("20"),
            starts_at=datetime(2026, 6, 1, 0, 0, 0),
            ends_at=datetime(2026, 5, 1, 0, 0, 0),
        )


@pytest.mark.asyncio
async def test_admin_create_discount_invalidates_cache() -> None:
    result = await create_discount()

    assert "admin:discounts:*" in result.redis_service.deleted_patterns
    assert "discounts:*" in result.redis_service.deleted_patterns
    assert "products:list:*" in result.redis_service.deleted_patterns
    assert "products:detail:*" in result.redis_service.deleted_patterns
    assert "products:slug:*" in result.redis_service.deleted_patterns
    assert "products:discounted:*" in result.redis_service.deleted_patterns
    assert "cart:*" in result.redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_create_discount_audit_log_created() -> None:
    result = await create_discount()

    assert result.audit_log_repository.logs[0]["event"] == "admin_discount_create"
    assert result.audit_log_repository.logs[0]["details"] == {
        "discount_id": 1,
        "type": "product",
        "discount_type": "percent",
        "product_ids": [55],
        "category_ids": [],
    }
