from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.admin_dashboard import get_admin_promo_codes
from source.db.models.choises.enum import UserRole
from source.services.admin_auth import PermissionService
from source.services.admin_promo_code import AdminPromoCodeService


class FakeRedisService:
    async def get(self, key: str):
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        return None


class FakePromoCodeRepository:
    async def admin_get_list(self, *, session, query):
        return []

    async def admin_count(self, *, session, query) -> int:
        return 0


class FakePromoCodeUsageRepository:
    async def count_grouped_by_promo_code_ids(self, *, session, promo_code_ids: list[int]) -> dict[int, int]:
        return {}


def build_user(*, role=UserRole.MANAGER):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False, is_blocked=False)


@pytest.mark.asyncio
async def test_admin_get_promo_codes_no_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_promo_codes.__dishka_orig_func__(
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.MANAGER),
            page="1",
            limit="50",
            q=None,
            is_active=None,
            discount_type=None,
            date_from=None,
            date_to=None,
            redis_service=FakeRedisService(),
            admin_promo_code_service=AdminPromoCodeService(),
            permission_service=PermissionService(),
            promo_code_repository=FakePromoCodeRepository(),
            promo_code_usage_repository=FakePromoCodeUsageRepository(),
        )

    assert exc_info.value.status_code == 403
