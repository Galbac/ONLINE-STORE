from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.admin_dashboard import get_admin_discount_detail, get_admin_discounts
from source.db.models.choises.enum import UserRole
from source.services.admin_auth import PermissionService
from source.services.admin_discount import AdminDiscountService
from source.services.admin_discount_cache import AdminDiscountCacheService


class FakeRedisService:
    async def get(self, key: str):
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        return None


class FakeDiscountRepository:
    async def admin_get_list(self, *, session, query):
        return []

    async def admin_count(self, *, session, query) -> int:
        return 0

    async def admin_get_by_id(self, *, session, discount_id: int):
        return None


class FakeDiscountProductRepository:
    async def get_products(self, *, session, discount_id: int):
        return []


class FakeDiscountCategoryRepository:
    async def get_categories(self, *, session, discount_id: int):
        return []


def build_user(*, role=UserRole.MANAGER):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False, is_blocked=False)


@pytest.mark.asyncio
async def test_admin_get_discounts_no_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_discounts.__dishka_orig_func__(
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.MANAGER),
            page="1",
            limit="50",
            q=None,
            type=None,
            discount_type=None,
            is_active=None,
            date_from=None,
            date_to=None,
            redis_service=FakeRedisService(),
            admin_discount_service=AdminDiscountService(),
            admin_discount_cache_service=AdminDiscountCacheService(),
            permission_service=PermissionService(),
            discount_repository=FakeDiscountRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_get_discount_detail_no_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_discount_detail.__dishka_orig_func__(
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.MANAGER),
            discount_id=1,
            redis_service=FakeRedisService(),
            admin_discount_service=AdminDiscountService(),
            admin_discount_cache_service=AdminDiscountCacheService(),
            permission_service=PermissionService(),
            discount_repository=FakeDiscountRepository(),
            discount_product_repository=FakeDiscountProductRepository(),
            discount_category_repository=FakeDiscountCategoryRepository(),
        )

    assert exc_info.value.status_code == 403
