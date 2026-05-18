from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.schemas.pydantic.delivery import DeliveryOptionsResponse
from source.services.delivery import DeliveryService
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
