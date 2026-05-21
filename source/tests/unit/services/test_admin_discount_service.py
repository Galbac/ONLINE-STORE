from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.category import CategoryNotFoundError
from source.errors.discount import DiscountConflictError, DiscountExpiredError, DiscountNotFoundError, EmptyDiscountUpdateError
from source.errors.product import ProductNotFoundError
from source.schemas.pydantic.discount import AdminDiscountCreateRequest, AdminDiscountDetailResponse, AdminDiscountListQueryParams, AdminDiscountListResponse, AdminDiscountUpdateRequest
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
        self.detail_calls = 0
        self.updated = []
        self.soft_deleted = []
        self.active_updates = []
        self.has_conflicts_result = False

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

    async def admin_get_by_id(self, *, session, discount_id: int):
        self.detail_calls += 1
        for discount in self.discounts:
            if discount.id == discount_id and not discount.is_deleted:
                return discount
        return None

    async def update(self, *, session, discount, data: dict):
        self.updated.append((discount.id, data))
        for field, value in data.items():
            setattr(discount, field, value)
        discount.updated_date = datetime(2026, 5, 12, 11, 0, 0)
        return discount

    async def soft_delete(self, *, session, discount, deleted_at: datetime, deleted_by: int):
        self.soft_deleted.append(discount.id)
        discount.is_deleted = True
        discount.is_active = False
        discount.deleted_at = deleted_at
        discount.deleted_by = deleted_by
        discount.updated_date = deleted_at
        return discount

    async def update_active(self, *, session, discount, is_active: bool):
        self.active_updates.append((discount.id, is_active))
        discount.is_active = is_active
        discount.updated_date = datetime(2026, 5, 12, 12, 0, 0)
        return discount

    async def has_conflicts(self, **kwargs) -> bool:
        return self.has_conflicts_result

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
        deleted_at=extra.get("deleted_at"),
        deleted_by=extra.get("deleted_by"),
        starts_at=extra.get("starts_at", datetime(2026, 5, 1, 0, 0, 0)),
        ends_at=extra.get("ends_at", datetime(2026, 5, 31, 23, 59, 59)),
        created_date=created_date,
        updated_date=extra.get("updated_date", created_date),
        applicable_product_id=extra.get("applicable_product_id"),
        applicable_category_id=extra.get("applicable_category_id"),
    )


class FakeDiscountProductRepository:
    def __init__(self, products=None) -> None:
        self.created = []
        self.replaced = []
        self.products = products if products is not None else [
            SimpleNamespace(id=55, name="Яблоки красные", price=Decimal("150.00")),
        ]
        self.get_calls = 0

    async def bulk_create(self, *, session, discount_id: int, product_ids: list[int]):
        self.created.append((discount_id, product_ids))
        return []

    async def get_products(self, *, session, discount_id: int):
        self.get_calls += 1
        return self.products

    async def replace_products(self, *, session, discount_id: int, product_ids: list[int]):
        self.replaced.append((discount_id, product_ids))
        self.products = [
            SimpleNamespace(id=product_id, name=f"Товар {product_id}", price=Decimal("100.00"))
            for product_id in product_ids
        ]
        return []


class FakeDiscountCategoryRepository:
    def __init__(self, categories=None) -> None:
        self.created = []
        self.replaced = []
        self.categories = categories if categories is not None else []
        self.get_calls = 0

    async def bulk_create(self, *, session, discount_id: int, category_ids: list[int]):
        self.created.append((discount_id, category_ids))
        return []

    async def get_categories(self, *, session, discount_id: int):
        self.get_calls += 1
        return self.categories

    async def replace_categories(self, *, session, discount_id: int, category_ids: list[int]):
        self.replaced.append((discount_id, category_ids))
        self.categories = [
            SimpleNamespace(id=category_id, name=f"Категория {category_id}")
            for category_id in category_ids
        ]
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


async def get_discount_detail(
    *,
    discount_id: int = 1,
    redis_service=None,
    role=UserRole.ADMIN,
    discount_repository=None,
    discount_product_repository=None,
    discount_category_repository=None,
):
    discount_repository = discount_repository or FakeDiscountRepository()
    discount_product_repository = discount_product_repository or FakeDiscountProductRepository()
    discount_category_repository = discount_category_repository or FakeDiscountCategoryRepository()
    response = await AdminDiscountService().get_discount_detail(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_user(role=role),
        discount_id=discount_id,
        permission_service=PermissionService(),
        discount_repository=discount_repository,
        discount_product_repository=discount_product_repository,
        discount_category_repository=discount_category_repository,
        admin_discount_cache_service=AdminDiscountCacheService(),
    )
    return SimpleNamespace(
        response=response,
        discount_repository=discount_repository,
        discount_product_repository=discount_product_repository,
        discount_category_repository=discount_category_repository,
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


async def update_discount(
    *,
    data: AdminDiscountUpdateRequest | None = None,
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
    discount_repository = discount_repository or FakeDiscountRepository()
    discount_product_repository = discount_product_repository or FakeDiscountProductRepository()
    discount_category_repository = discount_category_repository or FakeDiscountCategoryRepository()
    response = await AdminDiscountService().update_discount(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        discount_id=1,
        data=data or AdminDiscountUpdateRequest(
            name="Скидка на яблоки 25%",
            product_ids=[55, 56],
            category_ids=[],
            discount_type="percent",
            discount_value=Decimal("25"),
            starts_at=datetime(2026, 5, 1, 0, 0, 0),
            ends_at=datetime(2026, 6, 1, 0, 0, 0),
            is_active=True,
        ),
        commiter=commiter,
        permission_service=PermissionService(),
        discount_repository=discount_repository,
        discount_product_repository=discount_product_repository,
        discount_category_repository=discount_category_repository,
        product_repository=product_repository or FakeProductRepository(product_ids=[55, 56]),
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
        discount_repository=discount_repository,
        discount_product_repository=discount_product_repository,
        discount_category_repository=discount_category_repository,
    )


async def delete_discount(
    *,
    discount_id: int = 1,
    redis_service=None,
    role=UserRole.ADMIN,
    discount_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    discount_repository = discount_repository or FakeDiscountRepository()
    response = await AdminDiscountService().delete_discount(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        discount_id=discount_id,
        commiter=commiter,
        permission_service=PermissionService(),
        discount_repository=discount_repository,
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
        admin_discount_cache_service=AdminDiscountCacheService(),
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
        discount_repository=discount_repository,
    )


async def activate_discount(
    *,
    discount_id: int = 1,
    redis_service=None,
    role=UserRole.ADMIN,
    discount_repository=None,
    discount_product_repository=None,
    discount_category_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    discount_repository = discount_repository or FakeDiscountRepository()
    discount_product_repository = discount_product_repository or FakeDiscountProductRepository()
    discount_category_repository = discount_category_repository or FakeDiscountCategoryRepository()
    response = await AdminDiscountService().activate_discount(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        discount_id=discount_id,
        commiter=commiter,
        permission_service=PermissionService(),
        discount_repository=discount_repository,
        discount_product_repository=discount_product_repository,
        discount_category_repository=discount_category_repository,
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
        discount_repository=discount_repository,
        discount_product_repository=discount_product_repository,
        discount_category_repository=discount_category_repository,
    )


async def deactivate_discount(
    *,
    discount_id: int = 1,
    redis_service=None,
    role=UserRole.ADMIN,
    discount_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    discount_repository = discount_repository or FakeDiscountRepository()
    response = await AdminDiscountService().deactivate_discount(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        discount_id=discount_id,
        commiter=commiter,
        permission_service=PermissionService(),
        discount_repository=discount_repository,
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
        admin_discount_cache_service=AdminDiscountCacheService(),
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
        discount_repository=discount_repository,
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
async def test_admin_get_discount_detail_success() -> None:
    result = await get_discount_detail()

    assert result.response.id == 1
    assert result.response.name == "Скидка на яблоки"
    assert result.response.products[0].id == 55
    assert result.response.products[0].name == "Яблоки красные"
    assert result.response.products[0].price == Decimal("150.00")
    assert result.response.categories == []


@pytest.mark.asyncio
async def test_admin_get_discount_detail_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminDiscountDetailResponse(
        id=1,
        name="Скидка из кеша",
        type="product",
        discount_type="percent",
        discount_value=Decimal("20"),
        is_active=True,
        starts_at=datetime(2026, 5, 1, 0, 0, 0),
        ends_at=datetime(2026, 5, 31, 23, 59, 59),
        products=[],
        categories=[],
    )
    redis_service.values["admin:discounts:detail:1"] = cached_response.model_dump_json()
    repository = FakeDiscountRepository()

    result = await get_discount_detail(redis_service=redis_service, discount_repository=repository)

    assert result.response == cached_response
    assert repository.detail_calls == 0


@pytest.mark.asyncio
async def test_admin_get_discount_detail_not_found_error() -> None:
    with pytest.raises(DiscountNotFoundError):
        await get_discount_detail(discount_id=999)


@pytest.mark.asyncio
async def test_admin_get_discount_detail_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_discount_detail(role=UserRole.MANAGER)


@pytest.mark.asyncio
async def test_admin_get_discount_detail_response_is_cached() -> None:
    redis_service = FakeRedisService()

    await get_discount_detail(redis_service=redis_service)

    cache_key = "admin:discounts:detail:1"
    assert cache_key in redis_service.values
    assert redis_service.ttls[cache_key] == settings.discounts.admin_detail_cache_ttl_seconds


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


@pytest.mark.asyncio
async def test_admin_update_discount_success() -> None:
    result = await update_discount()

    assert result.response.id == 1
    assert result.response.name == "Скидка на яблоки 25%"
    assert result.response.discount_type == "percent"
    assert result.response.discount_value == Decimal("25")
    assert result.response.is_active is True
    assert result.response.updated_at == datetime(2026, 5, 12, 11, 0, 0)
    assert result.discount_product_repository.replaced == [(1, [55, 56])]
    assert result.discount_category_repository.replaced == [(1, [])]
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_update_discount_no_fields_error() -> None:
    with pytest.raises(EmptyDiscountUpdateError):
        await update_discount(data=AdminDiscountUpdateRequest())


@pytest.mark.asyncio
async def test_admin_update_discount_invalid_percent_error() -> None:
    with pytest.raises(ValueError):
        await update_discount(data=AdminDiscountUpdateRequest(discount_value=Decimal("101")))


@pytest.mark.asyncio
async def test_admin_update_discount_product_not_found_error() -> None:
    with pytest.raises(ProductNotFoundError):
        await update_discount(
            data=AdminDiscountUpdateRequest(product_ids=[55, 56]),
            product_repository=FakeProductRepository(product_ids=[55]),
        )


@pytest.mark.asyncio
async def test_admin_update_discount_category_not_found_error() -> None:
    with pytest.raises(CategoryNotFoundError):
        await update_discount(
            data=AdminDiscountUpdateRequest(category_ids=[2]),
            category_repository=FakeCategoryRepository(category_ids=[]),
        )


@pytest.mark.asyncio
async def test_admin_update_discount_invalidates_cache() -> None:
    result = await update_discount()

    assert "admin:discounts:*" in result.redis_service.deleted_patterns
    assert "discounts:*" in result.redis_service.deleted_patterns
    assert "products:list:*" in result.redis_service.deleted_patterns
    assert "products:detail:*" in result.redis_service.deleted_patterns
    assert "products:slug:*" in result.redis_service.deleted_patterns
    assert "products:discounted:*" in result.redis_service.deleted_patterns
    assert "cart:*" in result.redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_update_discount_audit_log_created() -> None:
    result = await update_discount()

    assert result.audit_log_repository.logs[0]["event"] == "admin_discount_update"
    assert result.audit_log_repository.logs[0]["details"]["discount_id"] == 1
    assert result.audit_log_repository.logs[0]["details"]["changes"]["name"] == {
        "old": "Скидка на яблоки",
        "new": "Скидка на яблоки 25%",
    }
    assert result.audit_log_repository.logs[0]["details"]["changes"]["product_ids"] == {
        "old": [55],
        "new": [55, 56],
    }


@pytest.mark.asyncio
async def test_admin_delete_discount_success() -> None:
    result = await delete_discount()

    assert result.response.message == "Скидка удалена"
    assert result.discount_repository.soft_deleted == [1]
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_delete_discount_not_found_error() -> None:
    with pytest.raises(DiscountNotFoundError):
        await delete_discount(discount_id=999)


@pytest.mark.asyncio
async def test_admin_delete_discount_sets_inactive_and_deleted_flags() -> None:
    result = await delete_discount()
    discount = result.discount_repository.discounts[0]

    assert discount.is_active is False
    assert discount.is_deleted is True
    assert discount.deleted_by == 1
    assert discount.deleted_at is not None


@pytest.mark.asyncio
async def test_admin_delete_discount_invalidates_cache() -> None:
    result = await delete_discount()

    assert "admin:discounts:*" in result.redis_service.deleted_patterns
    assert "discounts:*" in result.redis_service.deleted_patterns
    assert "products:list:*" in result.redis_service.deleted_patterns
    assert "products:detail:*" in result.redis_service.deleted_patterns
    assert "products:slug:*" in result.redis_service.deleted_patterns
    assert "products:discounted:*" in result.redis_service.deleted_patterns
    assert "cart:*" in result.redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_delete_discount_audit_log_created() -> None:
    result = await delete_discount()

    assert result.audit_log_repository.logs[0]["event"] == "admin_discount_delete"
    assert result.audit_log_repository.logs[0]["details"] == {
        "discount_id": 1,
        "name": "Скидка на яблоки",
        "type": "product",
        "discount_type": "percent",
    }


@pytest.mark.asyncio
async def test_admin_activate_discount_success() -> None:
    repository = FakeDiscountRepository(
        discounts=[
            build_discount(discount_id=1, name="Скидка на яблоки", is_active=False),
        ],
    )

    result = await activate_discount(discount_repository=repository)

    assert result.response.id == 1
    assert result.response.is_active is True
    assert result.response.message == "Скидка активирована"
    assert repository.active_updates == [(1, True)]
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_activate_discount_expired_error() -> None:
    repository = FakeDiscountRepository(
        discounts=[
            build_discount(
                discount_id=1,
                name="Скидка на яблоки",
                is_active=False,
                ends_at=datetime(2026, 1, 1, 0, 0, 0),
            ),
        ],
    )

    with pytest.raises(DiscountExpiredError):
        await activate_discount(discount_repository=repository)


@pytest.mark.asyncio
async def test_admin_activate_deleted_discount_not_found_error() -> None:
    deleted_discount = build_discount(discount_id=1, name="Скидка на яблоки", is_active=False)
    deleted_discount.is_deleted = True
    repository = FakeDiscountRepository(discounts=[deleted_discount])

    with pytest.raises(DiscountNotFoundError):
        await activate_discount(discount_repository=repository)


@pytest.mark.asyncio
async def test_admin_activate_discount_conflict_error() -> None:
    repository = FakeDiscountRepository(
        discounts=[
            build_discount(discount_id=1, name="Скидка на яблоки", is_active=False),
        ],
    )
    repository.has_conflicts_result = True

    with pytest.raises(DiscountConflictError):
        await activate_discount(discount_repository=repository)


@pytest.mark.asyncio
async def test_admin_activate_discount_invalidates_cache() -> None:
    repository = FakeDiscountRepository(
        discounts=[
            build_discount(discount_id=1, name="Скидка на яблоки", is_active=False),
        ],
    )

    result = await activate_discount(discount_repository=repository)

    assert "admin:discounts:*" in result.redis_service.deleted_patterns
    assert "discounts:*" in result.redis_service.deleted_patterns
    assert "products:list:*" in result.redis_service.deleted_patterns
    assert "products:detail:*" in result.redis_service.deleted_patterns
    assert "products:slug:*" in result.redis_service.deleted_patterns
    assert "products:discounted:*" in result.redis_service.deleted_patterns
    assert "cart:*" in result.redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_deactivate_discount_success() -> None:
    result = await deactivate_discount()

    assert result.response.id == 1
    assert result.response.is_active is False
    assert result.response.message == "Скидка отключена"
    assert result.discount_repository.active_updates == [(1, False)]
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_deactivate_discount_repeat_success() -> None:
    repository = FakeDiscountRepository(
        discounts=[
            build_discount(discount_id=1, name="Скидка на яблоки", is_active=False),
        ],
    )

    result = await deactivate_discount(discount_repository=repository)

    assert result.response.is_active is False
    assert repository.active_updates == [(1, False)]


@pytest.mark.asyncio
async def test_admin_deactivate_discount_not_found_error() -> None:
    with pytest.raises(DiscountNotFoundError):
        await deactivate_discount(discount_id=999)


@pytest.mark.asyncio
async def test_admin_deactivate_discount_invalidates_cache() -> None:
    result = await deactivate_discount()

    assert "admin:discounts:*" in result.redis_service.deleted_patterns
    assert "discounts:*" in result.redis_service.deleted_patterns
    assert "products:list:*" in result.redis_service.deleted_patterns
    assert "products:detail:*" in result.redis_service.deleted_patterns
    assert "products:slug:*" in result.redis_service.deleted_patterns
    assert "products:discounted:*" in result.redis_service.deleted_patterns
    assert "cart:*" in result.redis_service.deleted_patterns


@pytest.mark.asyncio
async def test_admin_deactivate_discount_audit_log_created() -> None:
    result = await deactivate_discount()

    assert result.audit_log_repository.logs[0]["event"] == "admin_discount_deactivate"
    assert result.audit_log_repository.logs[0]["details"] == {
        "discount_id": 1,
        "name": "Скидка на яблоки",
        "type": "product",
    }
