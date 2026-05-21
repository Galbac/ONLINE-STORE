from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.admin_dashboard import (
    create_admin_delivery_zone,
    delete_admin_delivery_zone,
    get_admin_delivery_settings,
    get_admin_delivery_zones,
    update_admin_delivery_zone,
    update_admin_delivery_settings,
)
from source.db.models.choises.enum import UserRole
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_delivery import AdminDeliveryService
from source.services.admin_delivery_cache import AdminDeliveryCacheService
from source.services.delivery_cache import DeliveryCacheService


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


class FakeDeliverySettingsRepository:
    async def get_or_create_default(self, *, session):
        return SimpleNamespace(
            delivery_enabled=True,
            pickup_enabled=True,
            min_order_amount=1000,
            base_price=250,
            free_from_amount=3000,
            has_time_slots=True,
            delivery_description="Доставка по городу",
            pickup_description="Самовывоз",
            default_city="Москва",
            currency="RUB",
            updated_date=None,
        ), False

    async def update(self, *, session, delivery_settings, data: dict):
        for field, value in data.items():
            setattr(delivery_settings, field, value)
        return delivery_settings


class FakeDeliveryZoneRepository:
    async def get_by_name_and_city(self, *, session, name: str, city: str):
        return None

    async def create(self, *, session, data):
        return SimpleNamespace(
            id=1,
            name=data.name,
            city=data.city,
            description=data.description,
            delivery_price=data.delivery_price,
            free_delivery_from=data.free_delivery_from,
            min_order_amount=data.min_order_amount,
            is_active=data.is_active,
            is_deleted=False,
            sort_order=data.sort_order,
            created_date=None,
            updated_date=None,
        )

    async def get_by_id(self, *, session, zone_id: int):
        return None

    async def update(self, *, session, zone, data: dict):
        return zone

    async def soft_delete(self, *, session, zone, deleted_by: int):
        return zone

    async def get_list(self, *, session, query):
        return []

    async def count(self, *, session, query) -> int:
        return 0


class FakeAuditLogRepository:
    async def create(self, *, session, **data):
        return SimpleNamespace(**data)


class FakeOrderRepository:
    async def exists_active_by_delivery_zone_id(self, *, session, delivery_zone_id: int) -> bool:
        return False


def build_user(*, role=UserRole.CUSTOMER):
    return SimpleNamespace(id=1, role=role, is_active=True, is_deleted=False, is_blocked=False)


@pytest.mark.asyncio
async def test_admin_delivery_settings_customer_role_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_delivery_settings.__dishka_orig_func__(
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.CUSTOMER),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_settings_repository=FakeDeliverySettingsRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_delivery_zones_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_delivery_zones.__dishka_orig_func__(
            page=1,
            limit=50,
            q=None,
            city=None,
            is_active=None,
            include_deleted=False,
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.CONTENT_MANAGER),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_zone_repository=FakeDeliveryZoneRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_delivery_zone_create_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_admin_delivery_zone.__dishka_orig_func__(
            request=SimpleNamespace(client=None, headers={}),
            payload={
                "name": "Центральная зона",
                "city": "Москва",
                "delivery_price": "250.00",
                "min_order_amount": "1000.00",
            },
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.CONTENT_MANAGER),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            delivery_cache_service=DeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_zone_repository=FakeDeliveryZoneRepository(),
            audit_log_service=AuditLogService(),
            admin_audit_log_repository=FakeAuditLogRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await update_admin_delivery_zone.__dishka_orig_func__(
            request=SimpleNamespace(client=None, headers={}),
            zone_id=1,
            payload={"name": "Новая зона"},
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.CONTENT_MANAGER),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            delivery_cache_service=DeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_zone_repository=FakeDeliveryZoneRepository(),
            audit_log_service=AuditLogService(),
            admin_audit_log_repository=FakeAuditLogRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_delivery_zone_delete_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await delete_admin_delivery_zone.__dishka_orig_func__(
            request=SimpleNamespace(client=None, headers={}),
            zone_id=1,
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.CONTENT_MANAGER),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            delivery_cache_service=DeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_zone_repository=FakeDeliveryZoneRepository(),
            order_repository=FakeOrderRepository(),
            audit_log_service=AuditLogService(),
            admin_audit_log_repository=FakeAuditLogRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_delivery_settings_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_delivery_settings.__dishka_orig_func__(
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.CONTENT_MANAGER),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_settings_repository=FakeDeliverySettingsRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_delivery_settings_non_access_token_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_admin_delivery_settings.__dishka_orig_func__(
            token_payload={"token_type": "refresh"},
            current_user=build_user(role=UserRole.ADMIN),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_settings_repository=FakeDeliverySettingsRepository(),
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await update_admin_delivery_settings.__dishka_orig_func__(
            request=SimpleNamespace(client=None, headers={}),
            payload={"delivery_enabled": False},
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.MANAGER),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            delivery_cache_service=DeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_settings_repository=FakeDeliverySettingsRepository(),
            audit_log_service=AuditLogService(),
            admin_audit_log_repository=FakeAuditLogRepository(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_empty_body_returns_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await update_admin_delivery_settings.__dishka_orig_func__(
            request=SimpleNamespace(client=None, headers={}),
            payload={},
            token_payload={"token_type": "access"},
            current_user=build_user(role=UserRole.ADMIN),
            commiter=FakeCommiter(),
            redis_service=FakeRedisService(),
            admin_delivery_service=AdminDeliveryService(),
            admin_delivery_cache_service=AdminDeliveryCacheService(),
            delivery_cache_service=DeliveryCacheService(),
            permission_service=PermissionService(),
            delivery_settings_repository=FakeDeliverySettingsRepository(),
            audit_log_service=AuditLogService(),
            admin_audit_log_repository=FakeAuditLogRepository(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Не передано ни одного поля для обновления"
