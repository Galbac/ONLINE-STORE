from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.product import ProductNotFoundError
from source.errors.promo_code import (
    EmptyPromoCodeUpdateError,
    PromoCodeAlreadyExistsError,
    PromoCodeNotFoundError,
    PromoCodeUsageLimitExceededError,
)
from source.schemas.pydantic.promo_code import AdminPromoCodeCreateRequest, AdminPromoCodeDetailResponse, AdminPromoCodeListQueryParams, AdminPromoCodeUpdateRequest
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_promo_code import AdminPromoCodeService


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

    async def delete_by_pattern(self, pattern: str) -> None:
        self.ttls[pattern] = 0


class FakePromoCodeRepository:
    def __init__(self, promo_codes=None) -> None:
        self.promo_codes = promo_codes if promo_codes is not None else [
            build_promo_code(promo_code_id=1, code="PROMO10", name="Скидка 10%", is_active=True),
            build_promo_code(promo_code_id=2, code="FIXED500", name="500 рублей", discount_type="fixed_amount", is_active=False),
            build_promo_code(promo_code_id=3, code="SUMMER", name="Летняя скидка", is_active=True),
        ]
        self.created = []
        self.detail_calls = 0
        self.updated = []
        self.soft_deleted = []
        self.usages_deleted = False

    async def admin_get_list(self, *, session, query: AdminPromoCodeListQueryParams):
        promo_codes = self._filter(query=query)
        promo_codes.sort(key=lambda promo_code: promo_code.created_date, reverse=True)
        return promo_codes[query.offset : query.offset + query.limit]

    async def admin_count(self, *, session, query: AdminPromoCodeListQueryParams) -> int:
        return len(self._filter(query=query))

    async def admin_get_by_id(self, *, session, promo_code_id: int):
        self.detail_calls += 1
        return next(
            (
                promo_code
                for promo_code in self.promo_codes
                if promo_code.id == promo_code_id and not getattr(promo_code, "is_deleted", False)
            ),
            None,
        )

    async def get_by_code(self, *, session, code: str):
        return next((promo_code for promo_code in self.promo_codes if promo_code.code == code), None)

    async def create(self, *, session, **data):
        promo_code = build_promo_code(
            promo_code_id=len(self.promo_codes) + 1,
            code=data["code"],
            name=data["name"],
            discount_type=data["discount_type"],
            is_active=data["is_active"],
        )
        promo_code.discount_value = data["discount_value"]
        promo_code.min_order_amount = data["min_order_amount"]
        promo_code.max_discount_amount = data["max_discount_amount"]
        promo_code.usage_limit = data["usage_limit"]
        promo_code.per_user_usage_limit = data["per_user_usage_limit"]
        promo_code.description = data["description"]
        promo_code.starts_at = data["starts_at"]
        promo_code.ends_at = data["ends_at"]
        promo_code.applicable_product_id = data["applicable_product_id"]
        promo_code.applicable_category_id = data["applicable_category_id"]
        self.created.append(data)
        self.promo_codes.append(promo_code)
        return promo_code

    async def update(self, *, session, promo_code, data: dict):
        self.updated.append((promo_code.id, data))
        for field, value in data.items():
            setattr(promo_code, field, value)
        promo_code.updated_date = datetime(2026, 5, 12, 11, 0, 0)
        return promo_code

    async def soft_delete(self, *, session, promo_code, deleted_at: datetime, deleted_by: int):
        promo_code.is_deleted = True
        promo_code.is_active = False
        promo_code.deleted_at = deleted_at
        promo_code.deleted_by = deleted_by
        self.soft_deleted.append((promo_code.id, deleted_at, deleted_by))
        return promo_code

    def _filter(self, *, query: AdminPromoCodeListQueryParams):
        promo_codes = list(self.promo_codes)
        if query.q is not None:
            q = query.q.lower()
            promo_codes = [
                promo_code
                for promo_code in promo_codes
                if q in promo_code.code.lower() or q in (promo_code.name or "").lower()
            ]
        if query.is_active is not None:
            promo_codes = [promo_code for promo_code in promo_codes if promo_code.is_active is query.is_active]
        if query.discount_type is not None:
            promo_codes = [promo_code for promo_code in promo_codes if promo_code.discount_type == query.discount_type]
        if query.date_from is not None:
            promo_codes = [promo_code for promo_code in promo_codes if promo_code.created_date.date() >= query.date_from]
        if query.date_to is not None:
            promo_codes = [promo_code for promo_code in promo_codes if promo_code.created_date.date() <= query.date_to]
        return promo_codes


class FakePromoCodeUsageRepository:
    def __init__(self, usage_counts=None) -> None:
        self.usage_counts = usage_counts or {}

    async def count_grouped_by_promo_code_ids(self, *, session, promo_code_ids: list[int]) -> dict[int, int]:
        return {
            promo_code_id: self.usage_counts.get(promo_code_id, 0)
            for promo_code_id in promo_code_ids
        }

    async def count_by_promo_code_id(self, *, session, promo_code_id: int) -> int:
        return self.usage_counts.get(promo_code_id, 0)


class FakePromoCodeProductRepository:
    def __init__(self) -> None:
        self.created = []
        self.products = [
            SimpleNamespace(id=55, name="Яблоки", price=Decimal("150.00")),
        ]

    async def bulk_create(self, *, session, promo_code_id: int, product_ids: list[int]):
        self.created.append((promo_code_id, product_ids))
        return []

    async def get_products(self, *, session, promo_code_id: int):
        return self.products

    async def replace_products(self, *, session, promo_code_id: int, product_ids: list[int]):
        self.created.append((promo_code_id, product_ids))
        self.products = [
            SimpleNamespace(id=product_id, name=f"Товар {product_id}", price=Decimal("100.00"))
            for product_id in product_ids
        ]
        return []


class FakePromoCodeCategoryRepository:
    def __init__(self) -> None:
        self.created = []
        self.categories = [
            SimpleNamespace(id=2, name="Фрукты"),
        ]

    async def bulk_create(self, *, session, promo_code_id: int, category_ids: list[int]):
        self.created.append((promo_code_id, category_ids))
        return []

    async def get_categories(self, *, session, promo_code_id: int):
        return self.categories

    async def replace_categories(self, *, session, promo_code_id: int, category_ids: list[int]):
        self.created.append((promo_code_id, category_ids))
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


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(
        id=1,
        role=role,
        is_active=True,
        is_deleted=False,
        is_blocked=False,
    )


def build_promo_code(
    *,
    promo_code_id: int,
    code: str,
    name: str | None,
    discount_type: str = "percent",
    is_active: bool = True,
    created_date=None,
):
    created_date = created_date or datetime(2026, 5, 12, 10, 0, 0) + timedelta(minutes=promo_code_id)
    return SimpleNamespace(
        id=promo_code_id,
        code=code,
        name=name,
        discount_type=discount_type,
        discount_value=Decimal("10"),
        min_order_amount=Decimal("1000.00"),
        max_discount_amount=Decimal("500.00"),
        usage_limit=100,
        per_user_usage_limit=1,
        description=None,
        applicable_product_id=None,
        applicable_category_id=None,
        is_deleted=False,
        deleted_at=None,
        deleted_by=None,
        is_active=is_active,
        starts_at=datetime(2026, 5, 1, 0, 0, 0),
        ends_at=datetime(2026, 5, 31, 23, 59, 59),
        created_date=created_date,
        updated_date=created_date,
    )


async def get_promo_codes(
    *,
    query=None,
    redis_service=None,
    role=UserRole.ADMIN,
    promo_code_repository=None,
    promo_code_usage_repository=None,
):
    return await AdminPromoCodeService().get_promo_codes(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_user(role=role),
        query=query or AdminPromoCodeListQueryParams(),
        permission_service=PermissionService(),
        promo_code_repository=promo_code_repository or FakePromoCodeRepository(),
        promo_code_usage_repository=promo_code_usage_repository or FakePromoCodeUsageRepository(),
    )


async def create_promo_code(
    *,
    data: AdminPromoCodeCreateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    promo_code_repository=None,
    promo_code_product_repository=None,
    promo_code_category_repository=None,
    product_repository=None,
    category_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    promo_code_product_repository = promo_code_product_repository or FakePromoCodeProductRepository()
    promo_code_category_repository = promo_code_category_repository or FakePromoCodeCategoryRepository()
    response = await AdminPromoCodeService().create_promo_code(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        data=data or AdminPromoCodeCreateRequest(
            code=" promo10 ",
            name="Скидка 10%",
            description="Промокод на первый заказ",
            discount_type="percent",
            discount_value=Decimal("10"),
            min_order_amount=Decimal("1000.00"),
            max_discount_amount=Decimal("500.00"),
            usage_limit=100,
            user_usage_limit=1,
            starts_at=datetime(2026, 5, 1, 0, 0, 0),
            ends_at=datetime(2026, 5, 31, 23, 59, 59),
            is_active=True,
            product_ids=[55],
            category_ids=[],
        ),
        commiter=commiter,
        permission_service=PermissionService(),
        promo_code_repository=promo_code_repository or FakePromoCodeRepository(promo_codes=[]),
        promo_code_product_repository=promo_code_product_repository,
        promo_code_category_repository=promo_code_category_repository,
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
        promo_code_product_repository=promo_code_product_repository,
        promo_code_category_repository=promo_code_category_repository,
    )


async def get_promo_code_detail(
    *,
    promo_code_id: int = 1,
    redis_service=None,
    role=UserRole.ADMIN,
    promo_code_repository=None,
    promo_code_usage_repository=None,
    promo_code_product_repository=None,
    promo_code_category_repository=None,
):
    promo_code_repository = promo_code_repository or FakePromoCodeRepository()
    promo_code_product_repository = promo_code_product_repository or FakePromoCodeProductRepository()
    promo_code_category_repository = promo_code_category_repository or FakePromoCodeCategoryRepository()
    response = await AdminPromoCodeService().get_promo_code_detail(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_user(role=role),
        promo_code_id=promo_code_id,
        permission_service=PermissionService(),
        promo_code_repository=promo_code_repository,
        promo_code_usage_repository=promo_code_usage_repository or FakePromoCodeUsageRepository(),
        promo_code_product_repository=promo_code_product_repository,
        promo_code_category_repository=promo_code_category_repository,
    )
    return SimpleNamespace(
        response=response,
        promo_code_repository=promo_code_repository,
        promo_code_product_repository=promo_code_product_repository,
        promo_code_category_repository=promo_code_category_repository,
    )


async def update_promo_code(
    *,
    data: AdminPromoCodeUpdateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    promo_code_repository=None,
    promo_code_usage_repository=None,
    promo_code_product_repository=None,
    promo_code_category_repository=None,
    product_repository=None,
    category_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    promo_code_repository = promo_code_repository or FakePromoCodeRepository()
    promo_code_product_repository = promo_code_product_repository or FakePromoCodeProductRepository()
    promo_code_category_repository = promo_code_category_repository or FakePromoCodeCategoryRepository()
    response = await AdminPromoCodeService().update_promo_code(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        promo_code_id=1,
        data=data or AdminPromoCodeUpdateRequest(
            code="promo15",
            name="Скидка 15%",
            description="Обновлённый промокод",
            discount_type="percent",
            discount_value=Decimal("15"),
            min_order_amount=Decimal("1500.00"),
            max_discount_amount=Decimal("700.00"),
            usage_limit=200,
            user_usage_limit=1,
            starts_at=datetime(2026, 5, 1, 0, 0, 0),
            ends_at=datetime(2026, 6, 1, 0, 0, 0),
            is_active=True,
            product_ids=[],
            category_ids=[],
        ),
        commiter=commiter,
        permission_service=PermissionService(),
        promo_code_repository=promo_code_repository,
        promo_code_usage_repository=promo_code_usage_repository or FakePromoCodeUsageRepository(),
        promo_code_product_repository=promo_code_product_repository,
        promo_code_category_repository=promo_code_category_repository,
        product_repository=product_repository or FakeProductRepository(),
        category_repository=category_repository or FakeCategoryRepository(),
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
        promo_code_repository=promo_code_repository,
        promo_code_product_repository=promo_code_product_repository,
        promo_code_category_repository=promo_code_category_repository,
    )


async def delete_promo_code(
    *,
    promo_code_id: int = 1,
    redis_service=None,
    role=UserRole.ADMIN,
    promo_code_repository=None,
    audit_log_repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    commiter = commiter or FakeCommiter()
    promo_code_repository = promo_code_repository or FakePromoCodeRepository()
    response = await AdminPromoCodeService().delete_promo_code(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        promo_code_id=promo_code_id,
        commiter=commiter,
        permission_service=PermissionService(),
        promo_code_repository=promo_code_repository,
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        audit_log_repository=audit_log_repository,
        commiter=commiter,
        promo_code_repository=promo_code_repository,
    )


@pytest.mark.asyncio
async def test_admin_get_promo_codes_success() -> None:
    response = await get_promo_codes()

    assert response.total == 3
    assert response.page == 1
    assert response.limit == 50
    assert response.pages == 1
    assert response.items[0].code == "SUMMER"


@pytest.mark.asyncio
async def test_admin_get_promo_codes_searches_by_q() -> None:
    response = await get_promo_codes(query=AdminPromoCodeListQueryParams(q="  500  "))

    assert response.total == 1
    assert response.items[0].code == "FIXED500"


@pytest.mark.asyncio
async def test_admin_get_promo_codes_filters_by_is_active() -> None:
    response = await get_promo_codes(query=AdminPromoCodeListQueryParams(is_active=False))

    assert response.total == 1
    assert response.items[0].is_active is False


@pytest.mark.asyncio
async def test_admin_get_promo_codes_usage_count() -> None:
    response = await get_promo_codes(
        promo_code_usage_repository=FakePromoCodeUsageRepository(usage_counts={1: 25}),
        query=AdminPromoCodeListQueryParams(q="PROMO10"),
    )

    assert response.items[0].usage_count == 25


@pytest.mark.asyncio
async def test_admin_get_promo_codes_pagination() -> None:
    response = await get_promo_codes(query=AdminPromoCodeListQueryParams(page=2, limit=2))

    assert response.total == 3
    assert response.pages == 2
    assert len(response.items) == 1
    assert response.items[0].code == "PROMO10"


@pytest.mark.asyncio
async def test_admin_get_promo_codes_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_promo_codes(role=UserRole.MANAGER)


@pytest.mark.asyncio
async def test_admin_get_promo_codes_response_is_cached() -> None:
    redis_service = FakeRedisService()

    await get_promo_codes(redis_service=redis_service)

    assert len(redis_service.values) == 1
    assert next(iter(redis_service.values.values())).startswith('{"items"')
    assert next(iter(redis_service.ttls.values())) == settings.promo_codes.admin_list_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_create_percent_promo_code_success() -> None:
    result = await create_promo_code()

    assert result.response.code == "PROMO10"
    assert result.response.discount_type == "percent"
    assert result.response.discount_value == Decimal("10")
    assert result.response.min_order_amount == Decimal("1000.00")
    assert result.response.usage_limit == 100
    assert result.response.user_usage_limit == 1
    assert result.response.is_active is True
    assert result.promo_code_product_repository.created == [(1, [55])]
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_create_fixed_amount_promo_code_success() -> None:
    result = await create_promo_code(
        data=AdminPromoCodeCreateRequest(
            code="fixed500",
            name="500 рублей",
            discount_type="fixed_amount",
            discount_value=Decimal("500"),
            is_active=True,
        ),
    )

    assert result.response.code == "FIXED500"
    assert result.response.discount_type == "fixed_amount"
    assert result.response.discount_value == Decimal("500")


def test_admin_create_promo_code_normalizes_code_uppercase() -> None:
    data = AdminPromoCodeCreateRequest(
        code=" promo10 ",
        name="Скидка 10%",
        discount_type="percent",
        discount_value=Decimal("10"),
    )

    assert data.code == "PROMO10"


@pytest.mark.asyncio
async def test_admin_create_promo_code_already_exists_error() -> None:
    with pytest.raises(PromoCodeAlreadyExistsError):
        await create_promo_code(promo_code_repository=FakePromoCodeRepository())


def test_admin_create_promo_code_percent_above_100_error() -> None:
    with pytest.raises(ValidationError):
        AdminPromoCodeCreateRequest(
            code="PROMO101",
            name="Скидка",
            discount_type="percent",
            discount_value=Decimal("101"),
        )


def test_admin_create_promo_code_starts_after_ends_error() -> None:
    with pytest.raises(ValidationError):
        AdminPromoCodeCreateRequest(
            code="PROMO10",
            name="Скидка",
            discount_type="percent",
            discount_value=Decimal("10"),
            starts_at=datetime(2026, 6, 1, 0, 0, 0),
            ends_at=datetime(2026, 5, 1, 0, 0, 0),
        )


@pytest.mark.asyncio
async def test_admin_create_promo_code_product_not_found_error() -> None:
    with pytest.raises(ProductNotFoundError):
        await create_promo_code(product_repository=FakeProductRepository(product_ids=[]))


@pytest.mark.asyncio
async def test_admin_create_promo_code_invalidates_cache() -> None:
    redis_service = FakeRedisService()

    await create_promo_code(redis_service=redis_service)

    assert redis_service.ttls["admin:promo_codes:*"] == 0


@pytest.mark.asyncio
async def test_admin_create_promo_code_audit_log_created() -> None:
    result = await create_promo_code()

    assert result.audit_log_repository.logs[0]["event"] == "admin_promo_code_create"
    assert result.audit_log_repository.logs[0]["details"] == {
        "promo_code_id": 1,
        "code": "PROMO10",
        "discount_type": "percent",
        "product_ids": [55],
        "category_ids": [],
    }


@pytest.mark.asyncio
async def test_admin_get_promo_code_detail_success() -> None:
    result = await get_promo_code_detail()

    assert result.response.id == 1
    assert result.response.code == "PROMO10"
    assert result.response.name == "Скидка 10%"
    assert result.response.description is None
    assert result.response.products[0].id == 55
    assert result.response.products[0].name == "Яблоки"
    assert result.response.categories[0].id == 2


@pytest.mark.asyncio
async def test_admin_get_promo_code_detail_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminPromoCodeDetailResponse(
        id=1,
        code="PROMO10",
        name="Из кеша",
        discount_type="percent",
        discount_value=Decimal("10"),
        min_order_amount=Decimal("1000.00"),
        max_discount_amount=Decimal("500.00"),
        usage_limit=100,
        usage_count=25,
        user_usage_limit=1,
        is_active=True,
        products=[],
        categories=[],
    )
    redis_service.values["admin:promo_codes:detail:1"] = cached_response.model_dump_json()
    repository = FakePromoCodeRepository()

    result = await get_promo_code_detail(redis_service=redis_service, promo_code_repository=repository)

    assert result.response == cached_response
    assert repository.detail_calls == 0


@pytest.mark.asyncio
async def test_admin_get_promo_code_detail_not_found_error() -> None:
    with pytest.raises(PromoCodeNotFoundError):
        await get_promo_code_detail(promo_code_id=999)


@pytest.mark.asyncio
async def test_admin_get_promo_code_detail_usage_count() -> None:
    result = await get_promo_code_detail(
        promo_code_usage_repository=FakePromoCodeUsageRepository(usage_counts={1: 25}),
    )

    assert result.response.usage_count == 25


@pytest.mark.asyncio
async def test_admin_get_promo_code_detail_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_promo_code_detail(role=UserRole.MANAGER)


@pytest.mark.asyncio
async def test_admin_update_promo_code_success() -> None:
    result = await update_promo_code()

    assert result.response.id == 1
    assert result.response.code == "PROMO15"
    assert result.response.name == "Скидка 15%"
    assert result.response.discount_type == "percent"
    assert result.response.discount_value == Decimal("15")
    assert result.response.is_active is True
    assert result.response.updated_at == datetime(2026, 5, 12, 11, 0, 0)
    assert result.promo_code_repository.updated[0][0] == 1
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_update_promo_code_code_already_exists_error() -> None:
    with pytest.raises(PromoCodeAlreadyExistsError):
        await update_promo_code(data=AdminPromoCodeUpdateRequest(code="FIXED500"))


@pytest.mark.asyncio
async def test_admin_update_promo_code_no_fields_error() -> None:
    with pytest.raises(EmptyPromoCodeUpdateError):
        await update_promo_code(data=AdminPromoCodeUpdateRequest())


@pytest.mark.asyncio
async def test_admin_update_promo_code_invalid_percent_error() -> None:
    with pytest.raises(ValueError):
        await update_promo_code(
            data=AdminPromoCodeUpdateRequest(
                discount_type="percent",
                discount_value=Decimal("101"),
            ),
        )


@pytest.mark.asyncio
async def test_admin_update_promo_code_usage_limit_less_than_usage_count_error() -> None:
    with pytest.raises(PromoCodeUsageLimitExceededError):
        await update_promo_code(
            data=AdminPromoCodeUpdateRequest(usage_limit=10),
            promo_code_usage_repository=FakePromoCodeUsageRepository(usage_counts={1: 25}),
        )


@pytest.mark.asyncio
async def test_admin_update_promo_code_invalidates_cache() -> None:
    result = await update_promo_code()

    assert result.redis_service.ttls["admin:promo_codes:*"] == 0
    assert result.redis_service.ttls["cart:*"] == 0


@pytest.mark.asyncio
async def test_admin_update_promo_code_audit_log_created() -> None:
    result = await update_promo_code()

    assert result.audit_log_repository.logs[0]["event"] == "admin_promo_code_update"
    assert result.audit_log_repository.logs[0]["details"]["promo_code_id"] == 1
    assert result.audit_log_repository.logs[0]["details"]["changes"]["code"] == {
        "old": "PROMO10",
        "new": "PROMO15",
    }


@pytest.mark.asyncio
async def test_admin_delete_promo_code_success() -> None:
    result = await delete_promo_code()

    assert result.response.message == "Промокод удалён"
    assert result.promo_code_repository.soft_deleted[0][0] == 1
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_delete_promo_code_not_found_error() -> None:
    with pytest.raises(PromoCodeNotFoundError):
        await delete_promo_code(promo_code_id=999)


@pytest.mark.asyncio
async def test_admin_delete_promo_code_sets_inactive_and_deleted() -> None:
    result = await delete_promo_code()
    promo_code = result.promo_code_repository.promo_codes[0]

    assert promo_code.is_active is False
    assert promo_code.is_deleted is True
    assert promo_code.deleted_by == 1
    assert promo_code.deleted_at is not None


@pytest.mark.asyncio
async def test_admin_delete_promo_code_does_not_delete_usages() -> None:
    result = await delete_promo_code()

    assert result.promo_code_repository.usages_deleted is False


@pytest.mark.asyncio
async def test_admin_delete_promo_code_invalidates_cache() -> None:
    result = await delete_promo_code()

    assert result.redis_service.ttls["admin:promo_codes:*"] == 0
    assert result.redis_service.ttls["cart:*"] == 0


@pytest.mark.asyncio
async def test_admin_delete_promo_code_audit_log_created() -> None:
    result = await delete_promo_code()

    assert result.audit_log_repository.logs[0]["event"] == "admin_promo_code_delete"
    assert result.audit_log_repository.logs[0]["details"] == {
        "promo_code_id": 1,
        "code": "PROMO10",
        "name": "Скидка 10%",
        "discount_type": "percent",
    }
