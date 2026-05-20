from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.admin_dashboard import get_admin_users
from source.db.models.choises.enum import UserRole
from source.services.admin_auth import PermissionService
from source.services.admin_user import AdminUserService


class FakeRedisService:
    async def get(self, key: str):
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        return None


class FakeUserRepository:
    async def admin_get_customers(self, *, session, query):
        return []

    async def admin_count_customers(self, *, session, query) -> int:
        return 0


class FakeOrderRepository:
    async def get_user_stats_grouped(self, *, session, user_ids: list[int]):
        return {}


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False)


@pytest.mark.asyncio
async def test_admin_get_users_no_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_users.__dishka_orig_func__(
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.CONTENT_MANAGER),
            page="1",
            limit="50",
            q=None,
            is_active=None,
            is_blocked=None,
            is_deleted=None,
            date_from=None,
            date_to=None,
            redis_service=FakeRedisService(),
            admin_user_service=AdminUserService(),
            permission_service=PermissionService(),
            user_repository=FakeUserRepository(),
            order_repository=FakeOrderRepository(),
        )

    assert exc_info.value.status_code == 403
