from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.admin_dashboard import get_admin_roles
from source.db.models.choises.enum import UserRole
from source.repositories.role import PermissionRepository, RoleRepository
from source.services.admin_auth import PermissionService
from source.services.role import RoleService


class FakeRedisService:
    async def get(self, key: str):
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        return None


def build_user(*, role=UserRole.CONTENT_MANAGER):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False, is_blocked=False)


@pytest.mark.asyncio
async def test_admin_get_roles_no_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_roles.__dishka_orig_func__(
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.CONTENT_MANAGER),
            redis_service=FakeRedisService(),
            role_service=RoleService(),
            permission_service=PermissionService(),
            role_repository=RoleRepository(),
            permission_repository=PermissionRepository(),
        )

    assert exc_info.value.status_code == 403
