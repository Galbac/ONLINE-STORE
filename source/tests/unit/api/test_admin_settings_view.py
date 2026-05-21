from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.admin_dashboard import get_admin_settings, update_admin_settings
from source.db.models.choises.enum import UserRole
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_settings import AdminSettingsService
from source.services.delivery_cache import DeliveryCacheService
from source.services.settings_cache import SettingsCacheService


class FakeRedisService:
    async def get(self, key: str):
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def delete_by_pattern(self, pattern: str) -> None:
        return None


class FakeCommiter:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeSettingsRepository:
    async def get_or_create_default(self, *, session):
        return SimpleNamespace(), False

    async def update(self, *, session, store_settings, data: dict):
        return store_settings


class FakeDeliverySettingsRepository:
    async def get_or_create_default(self, *, session):
        return SimpleNamespace(), False

    async def update(self, *, session, delivery_settings, data: dict):
        return delivery_settings


class FakeCartCacheService:
    async def invalidate_all_summaries(self, *, redis_service) -> None:
        return None


class FakeAuditLogRepository:
    async def create(self, *, session, **data):
        return SimpleNamespace(**data)


def build_user(*, role=UserRole.CUSTOMER):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False, is_blocked=False)


@pytest.mark.asyncio
async def test_admin_settings_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_settings.__dishka_orig_func__(
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.MANAGER),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_settings_service=AdminSettingsService(),
            settings_cache_service=SettingsCacheService(),
            permission_service=PermissionService(),
            settings_repository=FakeSettingsRepository(),
            delivery_settings_repository=FakeDeliverySettingsRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_settings_non_access_token_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_settings.__dishka_orig_func__(
            token_payload={"token_type": "refresh"},
            current_user=build_user(role=UserRole.ADMIN),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_settings_service=AdminSettingsService(),
            settings_cache_service=SettingsCacheService(),
            permission_service=PermissionService(),
            settings_repository=FakeSettingsRepository(),
            delivery_settings_repository=FakeDeliverySettingsRepository(),
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_settings_update_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await update_admin_settings.__dishka_orig_func__(
            request=SimpleNamespace(client=None, headers={}),
            payload={"shop_name": "Новый магазин"},
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.MANAGER),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_settings_service=AdminSettingsService(),
            settings_cache_service=SettingsCacheService(),
            delivery_cache_service=DeliveryCacheService(),
            cart_cache_service=FakeCartCacheService(),
            permission_service=PermissionService(),
            settings_repository=FakeSettingsRepository(),
            delivery_settings_repository=FakeDeliverySettingsRepository(),
            audit_log_service=AuditLogService(),
            admin_audit_log_repository=FakeAuditLogRepository(),
        )

    assert exc_info.value.status_code == 403
