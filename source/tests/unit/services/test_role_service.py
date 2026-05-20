from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.repositories.role import PermissionRepository, RoleRepository
from source.schemas.pydantic.admin_role import AdminRoleListResponse, AdminRoleResponse
from source.services.admin_auth import PermissionService
from source.services.role import RoleService


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


class FakeRoleRepository(RoleRepository):
    def __init__(self) -> None:
        self.calls = 0

    async def get_admin_roles(self, *, session=None) -> list[dict]:
        self.calls += 1
        roles = await super().get_admin_roles(session=session)
        return [*roles, {"code": "customer", "name": "Клиент", "description": "Покупатель"}]


class FakePermissionRepository(PermissionRepository):
    def __init__(self) -> None:
        self.calls = 0

    async def get_by_role_codes(self, *, session=None, role_codes: list[str]) -> dict[str, list[str]]:
        self.calls += 1
        return await super().get_by_role_codes(session=session, role_codes=role_codes)


def build_user(*, role=UserRole.ADMIN):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False, is_blocked=False)


async def get_roles(*, redis_service=None, role=UserRole.ADMIN, role_repository=None, permission_repository=None):
    return await RoleService().get_admin_roles(
        session=None,
        redis_service=redis_service or FakeRedisService(),
        user=build_user(role=role),
        permission_service=PermissionService(),
        role_repository=role_repository or FakeRoleRepository(),
        permission_repository=permission_repository or FakePermissionRepository(),
    )


@pytest.mark.asyncio
async def test_get_admin_roles_success() -> None:
    response = await get_roles()

    assert [item.code for item in response.items] == [
        "admin",
        "manager",
        "content_manager",
        "picker",
        "courier",
    ]


@pytest.mark.asyncio
async def test_get_admin_roles_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminRoleListResponse(
        items=[
            AdminRoleResponse(
                code="admin",
                name="Администратор",
                description="Полный доступ",
                permissions=["admin:dashboard:read"],
            ),
        ],
    )
    redis_service.values["admin:roles:list"] = cached_response.model_dump_json()
    role_repository = FakeRoleRepository()
    permission_repository = FakePermissionRepository()

    response = await get_roles(
        redis_service=redis_service,
        role_repository=role_repository,
        permission_repository=permission_repository,
    )

    assert response == cached_response
    assert role_repository.calls == 0
    assert permission_repository.calls == 0


@pytest.mark.asyncio
async def test_get_admin_roles_customer_not_returned() -> None:
    response = await get_roles()

    assert "customer" not in [item.code for item in response.items]


@pytest.mark.asyncio
async def test_get_admin_roles_no_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_roles(role=UserRole.CONTENT_MANAGER)


@pytest.mark.asyncio
async def test_get_admin_roles_permissions_returned_and_cached() -> None:
    redis_service = FakeRedisService()

    response = await get_roles(redis_service=redis_service)

    admin_role = next(item for item in response.items if item.code == "admin")
    assert "admin:staff:read" in admin_role.permissions
    assert "admin:staff:delete" in admin_role.permissions
    assert "admin:roles:read" in admin_role.permissions
    assert redis_service.ttls["admin:roles:list"] == settings.admin_staff.roles_cache_ttl_seconds
