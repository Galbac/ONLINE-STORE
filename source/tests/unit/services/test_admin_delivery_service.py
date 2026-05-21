from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from source.api.dependencies import resolve_access_token
from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import AdminAuthAccessDeniedError
from source.errors.delivery import (
    DeliveryZoneAlreadyExistsError,
    DeliveryZoneNotFoundError,
    EmptyDeliverySettingsUpdateError,
    EmptyDeliveryZoneUpdateError,
)
from source.schemas.pydantic.delivery import (
    AdminDeliverySettingsResponse,
    AdminDeliverySettingsUpdateRequest,
    AdminDeliveryZoneCreateRequest,
    AdminDeliveryZoneListQueryParams,
    AdminDeliveryZoneListResponse,
    AdminDeliveryZoneUpdateRequest,
)
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.admin_delivery import AdminDeliveryService
from source.services.admin_delivery_cache import AdminDeliveryCacheService
from source.services.delivery_cache import DeliveryCacheService
from source.utils.query_hash import build_query_hash


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def delete_by_pattern(self, pattern: str) -> None:
        self.deleted.append(pattern)


class FakeDeliverySettingsRepository:
    def __init__(self, delivery_settings=None) -> None:
        self.delivery_settings = delivery_settings
        self.get_or_create_calls = 0
        self.created_default = False
        self.updated = []

    async def get_or_create_default(self, *, session):
        self.get_or_create_calls += 1
        if self.delivery_settings is not None:
            return self.delivery_settings, False
        self.created_default = True
        self.delivery_settings = build_delivery_settings(
            pickup_comment="Самовывоз доступен из выбранных магазинов",
        )
        return self.delivery_settings, True

    async def update(self, *, session, delivery_settings, data: dict):
        self.updated.append(data)
        for field, value in data.items():
            setattr(delivery_settings, field, value)
        delivery_settings.updated_date = datetime(2026, 5, 12, 11, 0, 0)
        return delivery_settings


class FakeDeliveryZoneRepository:
    def __init__(self, zones=None, existing_zone=None) -> None:
        self.zones = zones if zones is not None else [
            build_delivery_zone(zone_id=3, name="Южная зона", city="Москва", sort_order=20),
            build_delivery_zone(zone_id=1, name="Центральная зона", city="Москва", description="Центральный район", sort_order=10),
            build_delivery_zone(zone_id=2, name="Зона Казань", city="Казань", is_active=False, sort_order=15),
            build_delivery_zone(zone_id=4, name="Удалённая зона", city="Москва", is_deleted=True, sort_order=1),
        ]
        self.existing_zone = existing_zone
        self.get_list_calls = 0
        self.count_calls = 0
        self.created = []
        self.updated = []

    async def get_by_id(self, *, session, zone_id: int):
        for zone in self.zones:
            if zone.id == zone_id:
                return zone
        return None

    async def get_by_name_and_city(self, *, session, name: str, city: str):
        if self.existing_zone is not None:
            return self.existing_zone
        for zone in self.zones:
            if zone.name.lower() == name.lower() and zone.city.lower() == city.lower() and not zone.is_deleted:
                return zone
        return None

    async def create(self, *, session, data: AdminDeliveryZoneCreateRequest):
        zone = build_delivery_zone(
            zone_id=99,
            name=data.name,
            city=data.city,
            description=data.description,
            delivery_price=data.delivery_price,
            free_delivery_from=data.free_delivery_from,
            min_order_amount=data.min_order_amount,
            is_active=data.is_active,
            sort_order=data.sort_order,
        )
        self.created.append(zone)
        return zone

    async def update(self, *, session, zone, data: dict):
        self.updated.append(data)
        for field, value in data.items():
            setattr(zone, field, value)
        zone.updated_date = datetime(2026, 5, 12, 11, 0, 0)
        return zone

    async def get_list(self, *, session, query: AdminDeliveryZoneListQueryParams):
        self.get_list_calls += 1
        zones = self._filter(query=query)
        zones.sort(key=lambda zone: (zone.sort_order, zone.name))
        return zones[query.offset:query.offset + query.limit]

    async def count(self, *, session, query: AdminDeliveryZoneListQueryParams) -> int:
        self.count_calls += 1
        return len(self._filter(query=query))

    def _filter(self, *, query: AdminDeliveryZoneListQueryParams):
        zones = list(self.zones)
        if not query.include_deleted:
            zones = [zone for zone in zones if not zone.is_deleted]
        if query.city is not None:
            zones = [zone for zone in zones if zone.city.lower() == query.city.lower()]
        if query.is_active is not None:
            zones = [zone for zone in zones if zone.is_active is query.is_active]
        if query.q is not None:
            q = query.q.lower()
            zones = [
                zone for zone in zones
                if q in zone.name.lower()
                or q in zone.city.lower()
                or (zone.description is not None and q in zone.description.lower())
            ]
        return zones


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


def build_delivery_settings(
    *,
    delivery_enabled: bool = True,
    pickup_enabled: bool = True,
    pickup_comment: str = "Самовывоз доступен из выбранных магазинов",
):
    return SimpleNamespace(
        id=1,
        delivery_enabled=delivery_enabled,
        pickup_enabled=pickup_enabled,
        min_order_amount=Decimal("1000.00"),
        base_price=Decimal("250.00"),
        free_from_amount=Decimal("3000.00"),
        has_time_slots=True,
        delivery_description="Доставка по городу",
        pickup_description=pickup_comment,
        default_city="Москва",
        currency="RUB",
        created_date=datetime(2026, 5, 12, 9, 0, 0),
        updated_date=datetime(2026, 5, 12, 10, 0, 0),
        internal_secret="hidden",
    )


def build_delivery_zone(
    *,
    zone_id: int,
    name: str,
    city: str,
    description: str | None = None,
    delivery_price: Decimal | None = Decimal("250.00"),
    free_delivery_from: Decimal | None = Decimal("3000.00"),
    min_order_amount: Decimal | None = Decimal("1000.00"),
    is_active: bool = True,
    is_deleted: bool = False,
    sort_order: int = 10,
):
    return SimpleNamespace(
        id=zone_id,
        name=name,
        city=city,
        description=description,
        delivery_price=delivery_price,
        free_delivery_from=free_delivery_from,
        min_order_amount=min_order_amount,
        is_active=is_active,
        is_deleted=is_deleted,
        sort_order=sort_order,
        created_date=datetime(2026, 5, 12, 10, 0, 0),
        updated_date=datetime(2026, 5, 12, 10, 0, 0),
    )


async def get_settings(
    *,
    redis_service=None,
    role=UserRole.ADMIN,
    repository=None,
    commiter=None,
):
    redis_service = redis_service or FakeRedisService()
    commiter = commiter or FakeCommiter()
    repository = repository or FakeDeliverySettingsRepository(build_delivery_settings())
    response = await AdminDeliveryService().get_settings(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        commiter=commiter,
        permission_service=PermissionService(),
        admin_delivery_cache_service=AdminDeliveryCacheService(),
        delivery_settings_repository=repository,
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        repository=repository,
        commiter=commiter,
    )


async def get_zones(
    *,
    query: AdminDeliveryZoneListQueryParams | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    repository=None,
):
    redis_service = redis_service or FakeRedisService()
    repository = repository or FakeDeliveryZoneRepository()
    response = await AdminDeliveryService().get_zones(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        query=query or AdminDeliveryZoneListQueryParams(),
        permission_service=PermissionService(),
        admin_delivery_cache_service=AdminDeliveryCacheService(),
        delivery_zone_repository=repository,
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        repository=repository,
    )


async def create_zone(
    *,
    data: AdminDeliveryZoneCreateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    repository=None,
    commiter=None,
    audit_log_repository=None,
):
    redis_service = redis_service or FakeRedisService()
    repository = repository or FakeDeliveryZoneRepository(zones=[])
    commiter = commiter or FakeCommiter()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    response = await AdminDeliveryService().create_zone(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        data=data or AdminDeliveryZoneCreateRequest(
            name=" Центральная зона ",
            city=" Москва ",
            description=" Центральный район города ",
            delivery_price=Decimal("250.00"),
            free_delivery_from=Decimal("3000.00"),
            min_order_amount=Decimal("1000.00"),
            is_active=True,
            sort_order=10,
        ),
        commiter=commiter,
        permission_service=PermissionService(),
        admin_delivery_cache_service=AdminDeliveryCacheService(),
        delivery_cache_service=DeliveryCacheService(),
        delivery_zone_repository=repository,
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        repository=repository,
        commiter=commiter,
        audit_log_repository=audit_log_repository,
    )


async def update_zone(
    *,
    zone_id: int = 1,
    data: AdminDeliveryZoneUpdateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    repository=None,
    commiter=None,
    audit_log_repository=None,
):
    redis_service = redis_service or FakeRedisService()
    repository = repository or FakeDeliveryZoneRepository(
        zones=[build_delivery_zone(zone_id=1, name="Центральная зона", city="Москва")],
    )
    commiter = commiter or FakeCommiter()
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    response = await AdminDeliveryService().update_zone(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        zone_id=zone_id,
        data=data or AdminDeliveryZoneUpdateRequest(name=" Новая зона "),
        commiter=commiter,
        permission_service=PermissionService(),
        admin_delivery_cache_service=AdminDeliveryCacheService(),
        delivery_cache_service=DeliveryCacheService(),
        delivery_zone_repository=repository,
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        repository=repository,
        commiter=commiter,
        audit_log_repository=audit_log_repository,
    )


async def update_settings(
    *,
    data: AdminDeliverySettingsUpdateRequest | None = None,
    redis_service=None,
    role=UserRole.ADMIN,
    repository=None,
    commiter=None,
    audit_log_repository=None,
):
    redis_service = redis_service or FakeRedisService()
    commiter = commiter or FakeCommiter()
    repository = repository or FakeDeliverySettingsRepository(build_delivery_settings())
    audit_log_repository = audit_log_repository or FakeAuditLogRepository()
    response = await AdminDeliveryService().update_settings(
        session=None,
        redis_service=redis_service,
        user=build_user(role=role),
        data=data or AdminDeliverySettingsUpdateRequest(delivery_enabled=False),
        commiter=commiter,
        permission_service=PermissionService(),
        admin_delivery_cache_service=AdminDeliveryCacheService(),
        delivery_cache_service=DeliveryCacheService(),
        delivery_settings_repository=repository,
        audit_log_service=AuditLogService(),
        admin_audit_log_repository=audit_log_repository,
    )
    return SimpleNamespace(
        response=response,
        redis_service=redis_service,
        repository=repository,
        commiter=commiter,
        audit_log_repository=audit_log_repository,
    )


@pytest.mark.asyncio
async def test_admin_delivery_settings_from_postgres_success() -> None:
    result = await get_settings()

    assert result.response.delivery_enabled is True
    assert result.response.pickup_enabled is True
    assert result.response.min_order_amount == Decimal("1000.00")
    assert result.response.base_delivery_price == Decimal("250.00")
    assert result.response.free_delivery_from == Decimal("3000.00")
    assert result.response.time_slots_enabled is True
    assert result.response.delivery_comment == "Доставка по городу"
    assert result.response.pickup_comment == "Самовывоз доступен из выбранных магазинов"
    assert result.response.default_city == "Москва"
    assert result.response.currency == "RUB"
    assert result.response.updated_at == datetime(2026, 5, 12, 10, 0, 0)


@pytest.mark.asyncio
async def test_admin_delivery_settings_from_redis_cache() -> None:
    redis_service = FakeRedisService()
    cached_response = AdminDeliverySettingsResponse(
        delivery_enabled=False,
        pickup_enabled=True,
        min_order_amount=Decimal("1500.00"),
        base_delivery_price=Decimal("300.00"),
        free_delivery_from=Decimal("4000.00"),
        time_slots_enabled=False,
        delivery_comment="Из кеша",
        pickup_comment="Самовывоз",
        default_city="Казань",
        currency="RUB",
        updated_at=datetime(2026, 5, 12, 10, 0, 0),
    )
    redis_service.values["admin:delivery:settings"] = cached_response.model_dump_json()
    repository = FakeDeliverySettingsRepository(build_delivery_settings())

    result = await get_settings(redis_service=redis_service, repository=repository)

    assert result.response == cached_response
    assert repository.get_or_create_calls == 0


@pytest.mark.asyncio
async def test_admin_delivery_settings_default_values_when_missing() -> None:
    commiter = FakeCommiter()
    result = await get_settings(repository=FakeDeliverySettingsRepository(None), commiter=commiter)

    assert result.response.delivery_enabled is True
    assert result.response.pickup_enabled is True
    assert result.response.default_city == "Москва"
    assert result.response.currency == "RUB"
    assert result.repository.created_default is True
    assert commiter.committed is True


@pytest.mark.asyncio
async def test_admin_delivery_settings_without_access_token_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await resolve_access_token(authorization=None, redis_service=FakeRedisService())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_delivery_settings_customer_role_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_settings(role=UserRole.CUSTOMER)


@pytest.mark.asyncio
async def test_admin_delivery_settings_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_settings(role=UserRole.CONTENT_MANAGER)


@pytest.mark.asyncio
async def test_admin_delivery_settings_does_not_return_service_fields() -> None:
    result = await get_settings()

    dumped = result.response.model_dump()

    assert "id" not in dumped
    assert "created_date" not in dumped
    assert "internal_secret" not in dumped


@pytest.mark.asyncio
async def test_admin_delivery_settings_response_is_cached() -> None:
    result = await get_settings()

    assert "admin:delivery:settings" in result.redis_service.values
    assert result.redis_service.ttls["admin:delivery:settings"] == settings.admin_delivery.settings_cache_ttl_seconds


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_delivery_enabled_success() -> None:
    result = await update_settings(data=AdminDeliverySettingsUpdateRequest(delivery_enabled=False))

    assert result.response.delivery_enabled is False
    assert result.repository.updated[0] == {"delivery_enabled": False}
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_pickup_enabled_success() -> None:
    result = await update_settings(data=AdminDeliverySettingsUpdateRequest(pickup_enabled=False))

    assert result.response.pickup_enabled is False
    assert result.repository.updated[0] == {"pickup_enabled": False}


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_base_delivery_price_success() -> None:
    result = await update_settings(data=AdminDeliverySettingsUpdateRequest(base_delivery_price=Decimal("350.00")))

    assert result.response.base_delivery_price == Decimal("350.00")
    assert result.repository.updated[0] == {"base_price": Decimal("350.00")}


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_empty_body_error() -> None:
    with pytest.raises(EmptyDeliverySettingsUpdateError):
        await update_settings(data=AdminDeliverySettingsUpdateRequest())


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_negative_price_error() -> None:
    with pytest.raises(ValueError, match="Стоимость доставки не может быть отрицательной"):
        await update_settings(data=AdminDeliverySettingsUpdateRequest(base_delivery_price=Decimal("-1.00")))


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_free_delivery_less_than_min_error() -> None:
    with pytest.raises(ValueError, match="Сумма бесплатной доставки"):
        await update_settings(data=AdminDeliverySettingsUpdateRequest(min_order_amount=Decimal("1000.00"), free_delivery_from=Decimal("900.00")))


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await update_settings(role=UserRole.MANAGER)


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_invalidates_cache() -> None:
    result = await update_settings()

    assert "admin:delivery:settings" in result.redis_service.deleted
    assert "delivery:options" in result.redis_service.deleted
    assert "delivery:calculate:*" in result.redis_service.deleted
    assert "delivery:time_slots:*" in result.redis_service.deleted
    assert "cart:summary:*" in result.redis_service.deleted


@pytest.mark.asyncio
async def test_admin_delivery_settings_update_audit_log_created() -> None:
    result = await update_settings(data=AdminDeliverySettingsUpdateRequest(base_delivery_price=Decimal("350.00")))

    assert result.audit_log_repository.logs[0]["event"] == "admin_delivery_settings_update"
    assert result.audit_log_repository.logs[0]["details"]["changes"]["base_delivery_price"] == {
        "old": "250.00",
        "new": "350.00",
    }


@pytest.mark.asyncio
async def test_admin_delivery_zones_from_postgres_success() -> None:
    result = await get_zones()

    assert [item.name for item in result.response.items] == ["Центральная зона", "Зона Казань", "Южная зона"]
    assert result.response.total == 3
    assert result.response.page == 1
    assert result.response.limit == 50
    assert result.response.pages == 1
    assert result.response.items[0].delivery_price == Decimal("250.00")
    assert result.response.items[0].description == "Центральный район"
    assert settings.admin_delivery.zones_cache_ttl_seconds == 300
    assert 300 in result.redis_service.ttls.values()


@pytest.mark.asyncio
async def test_admin_delivery_zones_from_redis_cache() -> None:
    query = AdminDeliveryZoneListQueryParams(city="Москва")
    cached_response = AdminDeliveryZoneListResponse.build(
        items=[],
        total=0,
        page=1,
        limit=50,
    )
    redis_service = FakeRedisService()
    redis_service.values[f"admin:delivery:zones:{build_query_hash(query.model_dump())}"] = cached_response.model_dump_json()
    repository = FakeDeliveryZoneRepository()

    result = await get_zones(query=query, redis_service=redis_service, repository=repository)

    assert result.response == cached_response
    assert repository.get_list_calls == 0
    assert repository.count_calls == 0


@pytest.mark.asyncio
async def test_admin_delivery_zones_filter_city() -> None:
    result = await get_zones(query=AdminDeliveryZoneListQueryParams(city=" Казань "))

    assert [item.city for item in result.response.items] == ["Казань"]


@pytest.mark.asyncio
async def test_admin_delivery_zones_filter_is_active() -> None:
    result = await get_zones(query=AdminDeliveryZoneListQueryParams(is_active=False))

    assert [item.name for item in result.response.items] == ["Зона Казань"]


@pytest.mark.asyncio
async def test_admin_delivery_zones_search_q() -> None:
    result = await get_zones(query=AdminDeliveryZoneListQueryParams(q=" центральный "))

    assert [item.name for item in result.response.items] == ["Центральная зона"]


@pytest.mark.asyncio
async def test_admin_delivery_zones_include_deleted_false_hides_deleted() -> None:
    result = await get_zones()

    assert all(not item.is_deleted for item in result.response.items)
    assert "Удалённая зона" not in [item.name for item in result.response.items]


@pytest.mark.asyncio
async def test_admin_delivery_zones_pagination() -> None:
    result = await get_zones(query=AdminDeliveryZoneListQueryParams(page=2, limit=2))

    assert [item.name for item in result.response.items] == ["Южная зона"]
    assert result.response.total == 3
    assert result.response.pages == 2


@pytest.mark.asyncio
async def test_admin_delivery_zones_sort_by_sort_order_and_name() -> None:
    repository = FakeDeliveryZoneRepository(
        [
            build_delivery_zone(zone_id=1, name="Ясенево", city="Москва", sort_order=10),
            build_delivery_zone(zone_id=2, name="Арбат", city="Москва", sort_order=10),
            build_delivery_zone(zone_id=3, name="Замоскворечье", city="Москва", sort_order=5),
        ],
    )

    result = await get_zones(repository=repository)

    assert [item.name for item in result.response.items] == ["Замоскворечье", "Арбат", "Ясенево"]


@pytest.mark.asyncio
async def test_admin_delivery_zones_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_zones(role=UserRole.CONTENT_MANAGER)


@pytest.mark.asyncio
async def test_admin_delivery_zones_include_deleted_requires_extra_permission() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await get_zones(role=UserRole.MANAGER, query=AdminDeliveryZoneListQueryParams(include_deleted=True))


@pytest.mark.asyncio
async def test_admin_delivery_zone_create_success() -> None:
    result = await create_zone()

    assert result.response.id == 99
    assert result.response.name == "Центральная зона"
    assert result.response.city == "Москва"
    assert result.response.description == "Центральный район города"
    assert result.response.delivery_price == Decimal("250.00")
    assert result.response.free_delivery_from == Decimal("3000.00")
    assert result.response.min_order_amount == Decimal("1000.00")
    assert result.response.is_active is True
    assert result.response.sort_order == 10
    assert result.commiter.committed is True


def test_admin_delivery_zone_create_empty_name_error() -> None:
    with pytest.raises(ValidationError):
        AdminDeliveryZoneCreateRequest(
            name=" ",
            city="Москва",
            delivery_price=Decimal("250.00"),
            min_order_amount=Decimal("1000.00"),
        )


def test_admin_delivery_zone_create_empty_city_error() -> None:
    with pytest.raises(ValidationError):
        AdminDeliveryZoneCreateRequest(
            name="Центральная зона",
            city=" ",
            delivery_price=Decimal("250.00"),
            min_order_amount=Decimal("1000.00"),
        )


def test_admin_delivery_zone_create_negative_delivery_price_error() -> None:
    with pytest.raises(ValidationError, match="Стоимость доставки"):
        AdminDeliveryZoneCreateRequest(
            name="Центральная зона",
            city="Москва",
            delivery_price=Decimal("-1.00"),
            min_order_amount=Decimal("1000.00"),
        )


def test_admin_delivery_zone_create_free_delivery_less_than_min_error() -> None:
    with pytest.raises(ValidationError, match="Сумма бесплатной доставки"):
        AdminDeliveryZoneCreateRequest(
            name="Центральная зона",
            city="Москва",
            delivery_price=Decimal("250.00"),
            free_delivery_from=Decimal("900.00"),
            min_order_amount=Decimal("1000.00"),
        )


@pytest.mark.asyncio
async def test_admin_delivery_zone_create_duplicate_name_city_error() -> None:
    repository = FakeDeliveryZoneRepository(
        zones=[],
        existing_zone=build_delivery_zone(zone_id=1, name="Центральная зона", city="Москва"),
    )

    with pytest.raises(DeliveryZoneAlreadyExistsError):
        await create_zone(repository=repository)


@pytest.mark.asyncio
async def test_admin_delivery_zone_create_without_permission_error() -> None:
    with pytest.raises(AdminAuthAccessDeniedError):
        await create_zone(role=UserRole.CONTENT_MANAGER)


@pytest.mark.asyncio
async def test_admin_delivery_zone_create_invalidates_cache() -> None:
    result = await create_zone()

    assert "admin:delivery:zones:*" in result.redis_service.deleted
    assert "delivery:calculate:*" in result.redis_service.deleted
    assert "delivery:options" in result.redis_service.deleted


@pytest.mark.asyncio
async def test_admin_delivery_zone_create_audit_log_created() -> None:
    result = await create_zone()

    assert result.audit_log_repository.logs[0]["event"] == "create_delivery_zone"
    assert result.audit_log_repository.logs[0]["user_id"] == 1
    assert result.audit_log_repository.logs[0]["ip_address"] == "127.0.0.1"
    assert result.audit_log_repository.logs[0]["user_agent"] == "pytest"
    assert result.audit_log_repository.logs[0]["details"]["actor_id"] == 1
    assert result.audit_log_repository.logs[0]["details"]["zone_id"] == 99


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_name_success() -> None:
    result = await update_zone(data=AdminDeliveryZoneUpdateRequest(name=" Новая зона "))

    assert result.response.name == "Новая зона"
    assert result.repository.updated[0] == {"name": "Новая зона"}
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_delivery_price_success() -> None:
    result = await update_zone(data=AdminDeliveryZoneUpdateRequest(delivery_price=Decimal("300.00")))

    assert result.response.delivery_price == Decimal("300.00")
    assert result.repository.updated[0] == {"delivery_price": Decimal("300.00")}


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_is_active_false_success() -> None:
    result = await update_zone(data=AdminDeliveryZoneUpdateRequest(is_active=False))

    assert result.response.is_active is False
    assert result.repository.updated[0] == {"is_active": False}


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_invalid_zone_id_error() -> None:
    with pytest.raises(ValueError, match="Неверный zone_id"):
        await update_zone(zone_id=0)


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_not_found_error() -> None:
    repository = FakeDeliveryZoneRepository(zones=[])

    with pytest.raises(DeliveryZoneNotFoundError):
        await update_zone(repository=repository)


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_deleted_zone_error() -> None:
    repository = FakeDeliveryZoneRepository(
        zones=[build_delivery_zone(zone_id=1, name="Удалённая зона", city="Москва", is_deleted=True)],
    )

    with pytest.raises(DeliveryZoneNotFoundError):
        await update_zone(repository=repository)


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_empty_body_error() -> None:
    with pytest.raises(EmptyDeliveryZoneUpdateError):
        await update_zone(data=AdminDeliveryZoneUpdateRequest())


def test_admin_delivery_zone_update_negative_price_error() -> None:
    with pytest.raises(ValidationError, match="Стоимость доставки"):
        AdminDeliveryZoneUpdateRequest(delivery_price=Decimal("-1.00"))


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_free_delivery_less_than_min_error() -> None:
    with pytest.raises(ValueError, match="Сумма бесплатной доставки"):
        await update_zone(data=AdminDeliveryZoneUpdateRequest(free_delivery_from=Decimal("900.00")))


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_duplicate_name_city_error() -> None:
    repository = FakeDeliveryZoneRepository(
        zones=[build_delivery_zone(zone_id=1, name="Центральная зона", city="Москва")],
        existing_zone=build_delivery_zone(zone_id=2, name="Новая зона", city="Москва"),
    )

    with pytest.raises(DeliveryZoneAlreadyExistsError):
        await update_zone(repository=repository, data=AdminDeliveryZoneUpdateRequest(name="Новая зона"))


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_invalidates_cache() -> None:
    result = await update_zone()

    assert "admin:delivery:zones:*" in result.redis_service.deleted
    assert "delivery:calculate:*" in result.redis_service.deleted
    assert "delivery:options" in result.redis_service.deleted


@pytest.mark.asyncio
async def test_admin_delivery_zone_update_audit_log_created() -> None:
    result = await update_zone(data=AdminDeliveryZoneUpdateRequest(delivery_price=Decimal("300.00")))

    assert result.audit_log_repository.logs[0]["event"] == "update_delivery_zone"
    assert result.audit_log_repository.logs[0]["user_id"] == 1
    assert result.audit_log_repository.logs[0]["ip_address"] == "127.0.0.1"
    assert result.audit_log_repository.logs[0]["user_agent"] == "pytest"
    assert result.audit_log_repository.logs[0]["details"]["actor_id"] == 1
    assert result.audit_log_repository.logs[0]["details"]["zone_id"] == 1
    assert result.audit_log_repository.logs[0]["details"]["changes"]["delivery_price"] == {
        "old": "250.00",
        "new": "300.00",
    }
