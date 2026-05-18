from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.errors.delivery import (
    DeliveryAddressAccessDeniedError,
    DeliveryDisabledError,
    DeliveryMinOrderAmountError,
)
from source.schemas.pydantic.delivery import DeliveryCalculateRequest, DeliveryCalculateResponse, DeliveryOptionsResponse
from source.services.delivery import DeliveryService, DeliveryZoneService
from source.services.delivery_cache import DeliveryCacheService


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
        self.values.pop(key, None)
        self.ttls.pop(key, None)


class FakeDeliverySettingsRepository:
    def __init__(self, delivery_settings: object | None = None) -> None:
        self.delivery_settings = delivery_settings or build_delivery_settings()
        self.get_settings_calls = 0

    async def get_settings(self, *, session):
        self.get_settings_calls += 1
        return self.delivery_settings


class FakePickupPointRepository:
    def __init__(self, has_active_points: bool = True) -> None:
        self.has_active_points_value = has_active_points
        self.has_active_points_calls = 0

    async def has_active_points(self, *, session) -> bool:
        self.has_active_points_calls += 1
        return self.has_active_points_value


class FakeAddressRepository:
    def __init__(self, address=None) -> None:
        self.address = address

    async def get_by_id(self, *, session, address_id: int):
        return self.address if self.address is not None and self.address.id == address_id else None


class FakeDeliveryZoneRepository:
    def __init__(self, zone=None) -> None:
        self.zone = zone or SimpleNamespace(id=1, name="Центральная зона", city="Москва", price=None)
        self.find_by_city_calls = 0

    async def find_by_city(self, *, session, city: str):
        self.find_by_city_calls += 1
        if self.zone is None or self.zone.city.lower() != city.lower():
            return None
        return self.zone


def build_delivery_settings(
    *,
    delivery_enabled: bool = True,
    pickup_enabled: bool = True,
):
    return SimpleNamespace(
        delivery_enabled=delivery_enabled,
        delivery_title="Доставка",
        delivery_description="Доставка по городу",
        min_order_amount=Decimal("1000.00"),
        base_price=Decimal("250.00"),
        free_from_amount=Decimal("3000.00"),
        has_time_slots=True,
        pickup_enabled=pickup_enabled,
        pickup_title="Самовывоз",
        pickup_description="Можно забрать заказ из магазина",
        pickup_price=Decimal("0"),
    )


async def execute_get_options(
    *,
    redis_service: FakeRedisService | None = None,
    delivery_settings_repository: FakeDeliverySettingsRepository | None = None,
    pickup_point_repository: FakePickupPointRepository | None = None,
) -> DeliveryOptionsResponse:
    return await DeliveryService().get_options(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        delivery_cache_service=DeliveryCacheService(),
        delivery_settings_repository=delivery_settings_repository or FakeDeliverySettingsRepository(),
        pickup_point_repository=pickup_point_repository or FakePickupPointRepository(),
    )


async def execute_calculate(
    *,
    data: DeliveryCalculateRequest | None = None,
    user_id: int | None = None,
    redis_service: FakeRedisService | None = None,
    delivery_settings_repository: FakeDeliverySettingsRepository | None = None,
    delivery_zone_repository: FakeDeliveryZoneRepository | None = None,
    address_repository: FakeAddressRepository | None = None,
) -> DeliveryCalculateResponse:
    return await DeliveryService().calculate(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        delivery_cache_service=DeliveryCacheService(),
        delivery_settings_repository=delivery_settings_repository or FakeDeliverySettingsRepository(),
        delivery_zone_service=DeliveryZoneService(),
        delivery_zone_repository=delivery_zone_repository or FakeDeliveryZoneRepository(),
        address_repository=address_repository or FakeAddressRepository(),
        user_id=user_id,
        data=data
        or DeliveryCalculateRequest(
            city="Москва",
            street="Тверская",
            house="10",
            apartment="15",
            order_amount=Decimal("2500.00"),
        ),
    )


@pytest.mark.asyncio
async def test_get_options_both_methods_enabled() -> None:
    response = await execute_get_options()

    assert response.delivery.enabled is True
    assert response.delivery.title == "Доставка"
    assert response.delivery.min_order_amount == Decimal("1000.00")
    assert response.delivery.base_price == Decimal("250.00")
    assert response.delivery.free_from_amount == Decimal("3000.00")
    assert response.delivery.has_time_slots is True
    assert response.pickup.enabled is True
    assert response.pickup.title == "Самовывоз"
    assert response.pickup.price == Decimal("0")
    assert response.pickup.has_pickup_points is True


@pytest.mark.asyncio
async def test_get_options_delivery_disabled() -> None:
    response = await execute_get_options(
        delivery_settings_repository=FakeDeliverySettingsRepository(
            build_delivery_settings(delivery_enabled=False),
        ),
    )

    assert response.delivery.enabled is False
    assert response.pickup.enabled is True


@pytest.mark.asyncio
async def test_get_options_pickup_disabled() -> None:
    response = await execute_get_options(
        delivery_settings_repository=FakeDeliverySettingsRepository(
            build_delivery_settings(pickup_enabled=False),
        ),
    )

    assert response.delivery.enabled is True
    assert response.pickup.enabled is False


@pytest.mark.asyncio
async def test_get_options_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    repository = FakeDeliverySettingsRepository()
    pickup_point_repository = FakePickupPointRepository()
    cached_response = DeliveryOptionsResponse(
        delivery={
            "enabled": False,
            "title": "Доставка",
            "description": "Доставка временно недоступна",
            "min_order_amount": Decimal("1500.00"),
            "base_price": Decimal("300.00"),
            "free_from_amount": None,
            "has_time_slots": False,
        },
        pickup={
            "enabled": True,
            "title": "Самовывоз",
            "description": "Заберите заказ из магазина",
            "price": Decimal("0"),
            "has_pickup_points": True,
        },
    )
    redis_service.values["delivery:options"] = cached_response.model_dump_json()

    response = await execute_get_options(
        redis_service=redis_service,
        delivery_settings_repository=repository,
        pickup_point_repository=pickup_point_repository,
    )

    assert response == cached_response
    assert repository.get_settings_calls == 0
    assert pickup_point_repository.has_active_points_calls == 0


@pytest.mark.asyncio
async def test_get_options_caches_response() -> None:
    redis_service = FakeRedisService()

    await execute_get_options(redis_service=redis_service)

    assert "delivery:options" in redis_service.values
    assert redis_service.ttls["delivery:options"] == settings.delivery_options.cache_ttl_seconds


@pytest.mark.asyncio
async def test_invalidate_options_deletes_cache() -> None:
    redis_service = FakeRedisService()
    redis_service.values["delivery:options"] = "{}"

    await DeliveryCacheService().invalidate_options(redis_service=redis_service)

    assert redis_service.deleted == ["delivery:options"]
    assert "delivery:options" not in redis_service.values


@pytest.mark.asyncio
async def test_calculate_delivery_success() -> None:
    redis_service = FakeRedisService()

    response = await execute_calculate(redis_service=redis_service)

    assert response.available is True
    assert response.delivery_price == Decimal("250.00")
    assert response.free_delivery_from == Decimal("3000.00")
    assert response.amount_left_for_free_delivery == Decimal("500.00")
    assert response.min_order_amount == Decimal("1000.00")
    assert response.zone is not None
    assert response.zone.id == 1
    assert response.zone.name == "Центральная зона"
    assert response.message == "Доставка доступна"
    assert redis_service.ttls[
        "delivery:calculate:5df751f22f0a52097e34a657bf980dd803919115f5876f500f400dcaf6b98f93"
    ] == settings.delivery_calculate.cache_ttl_seconds


@pytest.mark.asyncio
async def test_calculate_delivery_free_from_amount() -> None:
    response = await execute_calculate(
        data=DeliveryCalculateRequest(
            city="Москва",
            street="Тверская",
            house="10",
            order_amount=Decimal("3000.00"),
        ),
    )

    assert response.available is True
    assert response.delivery_price == Decimal("0")
    assert response.amount_left_for_free_delivery == Decimal("0")


@pytest.mark.asyncio
async def test_calculate_delivery_min_order_amount_error() -> None:
    with pytest.raises(DeliveryMinOrderAmountError):
        await execute_calculate(
            data=DeliveryCalculateRequest(
                city="Москва",
                street="Тверская",
                house="10",
                order_amount=Decimal("999.99"),
            ),
        )


@pytest.mark.asyncio
async def test_calculate_delivery_disabled_error() -> None:
    with pytest.raises(DeliveryDisabledError):
        await execute_calculate(
            delivery_settings_repository=FakeDeliverySettingsRepository(
                build_delivery_settings(delivery_enabled=False),
            ),
        )


@pytest.mark.asyncio
async def test_calculate_delivery_address_out_of_zone() -> None:
    response = await execute_calculate(
        data=DeliveryCalculateRequest(
            city="Санкт-Петербург",
            street="Невский",
            house="10",
            order_amount=Decimal("2500.00"),
        ),
    )

    assert response.available is False
    assert response.delivery_price is None
    assert response.message == "Доставка по этому адресу недоступна"


@pytest.mark.asyncio
async def test_calculate_delivery_address_id_other_user_error() -> None:
    address = SimpleNamespace(
        id=5,
        user_id=2,
        city="Москва",
        street="Тверская",
        house="10",
        apartment="15",
        is_deleted=False,
    )

    with pytest.raises(DeliveryAddressAccessDeniedError):
        await execute_calculate(
            data=DeliveryCalculateRequest(address_id=5, order_amount=Decimal("2500.00")),
            user_id=1,
            address_repository=FakeAddressRepository(address),
        )


@pytest.mark.asyncio
async def test_calculate_delivery_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    delivery_zone_repository = FakeDeliveryZoneRepository()
    cached_response = DeliveryCalculateResponse(
        available=True,
        delivery_price=Decimal("111.00"),
        free_delivery_from=Decimal("3000.00"),
        amount_left_for_free_delivery=Decimal("500.00"),
        min_order_amount=Decimal("1000.00"),
        zone={"id": 1, "name": "Центральная зона"},
        message="Доставка доступна",
    )
    redis_service.values[
        "delivery:calculate:5df751f22f0a52097e34a657bf980dd803919115f5876f500f400dcaf6b98f93"
    ] = cached_response.model_dump_json()

    response = await execute_calculate(
        redis_service=redis_service,
        delivery_zone_repository=delivery_zone_repository,
    )

    assert response == cached_response
    assert delivery_zone_repository.find_by_city_calls == 0
    assert redis_service.ttls == {}
