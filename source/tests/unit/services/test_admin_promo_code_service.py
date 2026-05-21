from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.schemas.pydantic.promo_code import AdminPromoCodeListQueryParams
from source.services.admin_auth import PermissionService
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


class FakePromoCodeRepository:
    def __init__(self, promo_codes=None) -> None:
        self.promo_codes = promo_codes if promo_codes is not None else [
            build_promo_code(promo_code_id=1, code="PROMO10", name="Скидка 10%", is_active=True),
            build_promo_code(promo_code_id=2, code="FIXED500", name="500 рублей", discount_type="fixed_amount", is_active=False),
            build_promo_code(promo_code_id=3, code="SUMMER", name="Летняя скидка", is_active=True),
        ]

    async def admin_get_list(self, *, session, query: AdminPromoCodeListQueryParams):
        promo_codes = self._filter(query=query)
        promo_codes.sort(key=lambda promo_code: promo_code.created_date, reverse=True)
        return promo_codes[query.offset : query.offset + query.limit]

    async def admin_count(self, *, session, query: AdminPromoCodeListQueryParams) -> int:
        return len(self._filter(query=query))

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
        usage_limit=100,
        per_user_usage_limit=1,
        is_active=is_active,
        starts_at=datetime(2026, 5, 1, 0, 0, 0),
        ends_at=datetime(2026, 5, 31, 23, 59, 59),
        created_date=created_date,
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
