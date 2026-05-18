from datetime import date, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.errors.delivery import (
    DeliveryAddressAccessDeniedError,
    DeliveryDateInPastError,
    DeliveryDisabledError,
    DeliveryMinOrderAmountError,
    PickupPointInactiveError,
    PickupPointNotFoundError,
)
from source.schemas.pydantic.delivery import (
    DeliveryCalculateRequest,
    DeliveryCalculateResponse,
    DeliveryOptionsResponse,
    DeliveryTimeSlotsQueryParams,
    DeliveryTimeSlotsResponse,
    PickupPointDetailResponse,
    PickupPointListQueryParams,
    PickupPointListResponse,
)
from source.services.delivery import DeliveryService, DeliveryTimeSlotService, DeliveryZoneService
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

    async def delete_by_pattern(self, pattern: str) -> None:
        prefix = pattern.removesuffix("*")
        keys = [key for key in self.values if key.startswith(prefix)]
        for key in keys:
            await self.delete(key)


class FakeDeliverySettingsRepository:
    def __init__(self, delivery_settings: object | None = None) -> None:
        self.delivery_settings = delivery_settings or build_delivery_settings()
        self.get_settings_calls = 0

    async def get_settings(self, *, session):
        self.get_settings_calls += 1
        return self.delivery_settings


class FakePickupPointRepository:
    def __init__(self, has_active_points: bool = True, pickup_points: list[object] | None = None) -> None:
        self.has_active_points_value = has_active_points
        self.pickup_points = pickup_points if pickup_points is not None else [
            build_pickup_point(point_id=1, name="Магазин на Тверской", city="Москва", sort_order=10),
            build_pickup_point(point_id=2, name="Магазин на Арбате", city="Москва", sort_order=20),
            build_pickup_point(point_id=3, name="Склад", city="Казань", is_active=False, sort_order=30),
        ]
        self.has_active_points_calls = 0
        self.get_list_calls = 0
        self.get_by_id_calls = 0
        self.get_active_by_id_calls = 0

    async def has_active_points(self, *, session) -> bool:
        self.has_active_points_calls += 1
        return self.has_active_points_value

    async def get_list(self, *, session, query: PickupPointListQueryParams):
        self.get_list_calls += 1
        points = self._filter(query=query)
        points.sort(key=lambda point: (point.sort_order, point.name))
        return points[query.offset : query.offset + query.limit]

    async def count(self, *, session, query: PickupPointListQueryParams) -> int:
        return len(self._filter(query=query))

    async def get_by_id(self, *, session, pickup_point_id: int):
        self.get_by_id_calls += 1
        return next((point for point in self.pickup_points if point.id == pickup_point_id), None)

    async def get_active_by_id(self, *, session, pickup_point_id: int):
        self.get_active_by_id_calls += 1
        point = next((point for point in self.pickup_points if point.id == pickup_point_id), None)
        return point if point is not None and point.is_active else None

    def _filter(self, *, query: PickupPointListQueryParams) -> list[object]:
        points = self.pickup_points
        if query.only_active:
            points = [point for point in points if point.is_active]
        if query.city is not None:
            points = [point for point in points if point.city.lower() == query.city.lower()]
        return list(points)


class FakeDeliveryTimeSlotRepository:
    def __init__(self, slots: list[object] | None = None) -> None:
        self.slots = slots if slots is not None else [
            build_time_slot(slot_id=1, start=time(10), end=time(12), orders_limit=2),
            build_time_slot(slot_id=2, start=time(12), end=time(14), orders_limit=1),
        ]
        self.get_by_day_calls = 0

    async def get_by_day(self, *, session, date_, delivery_type: str, pickup_point_id: int | None = None):
        self.get_by_day_calls += 1
        return [
            slot
            for slot in self.slots
            if slot.delivery_type == delivery_type and (delivery_type != "pickup" or slot.pickup_point_id in {None, pickup_point_id})
        ]


class FakeOrderRepository:
    def __init__(self, counts_by_slot_id: dict[int, int] | None = None) -> None:
        self.counts_by_slot_id = counts_by_slot_id or {}

    async def count_orders_by_time_slot(
        self,
        *,
        session,
        delivery_date,
        delivery_time_slot_id: int,
        delivery_type: str,
        pickup_point_id: int | None = None,
    ) -> int:
        return self.counts_by_slot_id.get(delivery_time_slot_id, 0)


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


def build_pickup_point(
    *,
    point_id: int,
    name: str,
    city: str,
    is_active: bool = True,
    sort_order: int = 0,
):
    return SimpleNamespace(
        id=point_id,
        name=name,
        city=city,
        address="ул. Тверская, 10",
        working_hours="Пн-Вс 09:00–22:00",
        phone="+79990000000",
        description="Вход со стороны улицы",
        is_active=is_active,
        latitude=Decimal("55.755800"),
        longitude=Decimal("37.617300"),
        sort_order=sort_order,
    )


def build_time_slot(
    *,
    slot_id: int,
    start: time,
    end: time,
    delivery_type: str = "delivery",
    pickup_point_id: int | None = None,
    orders_limit: int = 10,
    is_active: bool = True,
):
    return SimpleNamespace(
        id=slot_id,
        delivery_type=delivery_type,
        pickup_point_id=pickup_point_id,
        start_time=start,
        end_time=end,
        label=f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}",
        orders_limit=orders_limit,
        is_active=is_active,
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


async def execute_get_pickup_points(
    *,
    redis_service: FakeRedisService | None = None,
    pickup_point_repository: FakePickupPointRepository | None = None,
    query: PickupPointListQueryParams | None = None,
) -> PickupPointListResponse:
    return await DeliveryService().get_pickup_points(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        delivery_cache_service=DeliveryCacheService(),
        pickup_point_repository=pickup_point_repository or FakePickupPointRepository(),
        query=query or PickupPointListQueryParams(),
    )


async def execute_get_pickup_point_by_id(
    *,
    redis_service: FakeRedisService | None = None,
    pickup_point_repository: FakePickupPointRepository | None = None,
    point_id: int = 1,
) -> PickupPointDetailResponse:
    return await DeliveryService().get_pickup_point_by_id(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        delivery_cache_service=DeliveryCacheService(),
        pickup_point_repository=pickup_point_repository or FakePickupPointRepository(),
        point_id=point_id,
    )


async def execute_get_time_slots(
    *,
    redis_service: FakeRedisService | None = None,
    delivery_settings_repository: FakeDeliverySettingsRepository | None = None,
    delivery_time_slot_repository: FakeDeliveryTimeSlotRepository | None = None,
    pickup_point_repository: FakePickupPointRepository | None = None,
    order_repository: FakeOrderRepository | None = None,
    query: DeliveryTimeSlotsQueryParams | None = None,
) -> DeliveryTimeSlotsResponse:
    return await DeliveryTimeSlotService().get_available_slots(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        delivery_cache_service=DeliveryCacheService(),
        delivery_settings_repository=delivery_settings_repository or FakeDeliverySettingsRepository(),
        delivery_time_slot_repository=delivery_time_slot_repository or FakeDeliveryTimeSlotRepository(),
        pickup_point_repository=pickup_point_repository or FakePickupPointRepository(),
        order_repository=order_repository or FakeOrderRepository(),
        query=query or DeliveryTimeSlotsQueryParams(date=date.today() + timedelta(days=1), delivery_type="delivery"),
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


@pytest.mark.asyncio
async def test_get_pickup_points_success() -> None:
    response = await execute_get_pickup_points()

    assert response.total == 2
    assert response.limit == 50
    assert response.offset == 0
    assert [point.name for point in response.items] == ["Магазин на Тверской", "Магазин на Арбате"]
    assert response.items[0].city == "Москва"


@pytest.mark.asyncio
async def test_get_pickup_points_filter_by_city() -> None:
    response = await execute_get_pickup_points(
        query=PickupPointListQueryParams(city="  москва  "),
    )

    assert response.total == 2
    assert {point.city for point in response.items} == {"Москва"}


@pytest.mark.asyncio
async def test_get_pickup_points_only_active_true() -> None:
    response = await execute_get_pickup_points(query=PickupPointListQueryParams(only_active=True))

    assert all(point.is_active for point in response.items)
    assert response.total == 2


@pytest.mark.asyncio
async def test_get_pickup_points_pagination() -> None:
    response = await execute_get_pickup_points(query=PickupPointListQueryParams(limit=1, offset=1))

    assert response.total == 2
    assert len(response.items) == 1
    assert response.items[0].name == "Магазин на Арбате"


@pytest.mark.asyncio
async def test_get_pickup_points_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    repository = FakePickupPointRepository()
    query = PickupPointListQueryParams()
    cached_response = PickupPointListResponse(
        items=[
            {
                "id": 10,
                "name": "Кешированная точка",
                "city": "Москва",
                "address": "ул. Тверская, 10",
                "is_active": True,
            },
        ],
        total=1,
        limit=50,
        offset=0,
    )
    from source.utils.query_hash import build_query_hash

    redis_service.values[f"delivery:pickup_points:{build_query_hash(query.model_dump())}"] = cached_response.model_dump_json()

    response = await execute_get_pickup_points(
        redis_service=redis_service,
        pickup_point_repository=repository,
        query=query,
    )

    assert response == cached_response
    assert repository.get_list_calls == 0


@pytest.mark.asyncio
async def test_get_pickup_points_inactive_points_not_returned_by_default() -> None:
    response = await execute_get_pickup_points()

    assert {point.id for point in response.items} == {1, 2}


@pytest.mark.asyncio
async def test_get_pickup_point_by_id_success() -> None:
    response = await execute_get_pickup_point_by_id()

    assert response.id == 1
    assert response.name == "Магазин на Тверской"
    assert response.description == "Вход со стороны улицы"
    assert not hasattr(response, "created_date")


@pytest.mark.asyncio
async def test_get_pickup_point_by_id_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    repository = FakePickupPointRepository()
    cached_response = PickupPointDetailResponse(
        id=1,
        name="Кешированная точка",
        city="Москва",
        address="ул. Тверская, 10",
        is_active=True,
        description="Вход",
    )
    redis_service.values["delivery:pickup_point:1"] = cached_response.model_dump_json()

    response = await execute_get_pickup_point_by_id(redis_service=redis_service, pickup_point_repository=repository)

    assert response == cached_response
    assert repository.get_by_id_calls == 0


@pytest.mark.asyncio
async def test_get_pickup_point_by_id_not_found_error() -> None:
    with pytest.raises(PickupPointNotFoundError):
        await execute_get_pickup_point_by_id(point_id=999)


@pytest.mark.asyncio
async def test_get_pickup_point_by_id_inactive_error() -> None:
    with pytest.raises(PickupPointInactiveError):
        await execute_get_pickup_point_by_id(point_id=3)


@pytest.mark.asyncio
async def test_get_delivery_time_slots_success() -> None:
    response = await execute_get_time_slots()

    assert response.delivery_type == "delivery"
    assert [slot.label for slot in response.items] == ["10:00–12:00", "12:00–14:00"]
    assert all(slot.available for slot in response.items)


@pytest.mark.asyncio
async def test_get_pickup_time_slots_success() -> None:
    response = await execute_get_time_slots(
        delivery_time_slot_repository=FakeDeliveryTimeSlotRepository(
            [build_time_slot(slot_id=3, start=time(10), end=time(12), delivery_type="pickup", pickup_point_id=1)],
        ),
        query=DeliveryTimeSlotsQueryParams(
            date=date.today() + timedelta(days=1),
            delivery_type="pickup",
            pickup_point_id=1,
        ),
    )

    assert response.delivery_type == "pickup"
    assert len(response.items) == 1
    assert response.items[0].id == 3


@pytest.mark.asyncio
async def test_get_time_slots_date_in_past_error() -> None:
    with pytest.raises(DeliveryDateInPastError):
        await execute_get_time_slots(
            query=DeliveryTimeSlotsQueryParams(date=date(2000, 1, 1), delivery_type="delivery"),
        )


def test_time_slots_invalid_delivery_type_error() -> None:
    with pytest.raises(Exception):
        DeliveryTimeSlotsQueryParams(date=date.today() + timedelta(days=1), delivery_type="courier")


@pytest.mark.asyncio
async def test_get_time_slots_full_slot_available_false() -> None:
    response = await execute_get_time_slots(order_repository=FakeOrderRepository({2: 1}))

    full_slot = next(slot for slot in response.items if slot.id == 2)
    assert full_slot.available is False
    assert full_slot.reason == "Интервал заполнен"
    assert full_slot.orders_count == 1


@pytest.mark.asyncio
async def test_get_time_slots_disabled_slot_not_returned() -> None:
    response = await execute_get_time_slots(
        delivery_time_slot_repository=FakeDeliveryTimeSlotRepository(
            [
                build_time_slot(slot_id=1, start=time(10), end=time(12), is_active=True),
                build_time_slot(slot_id=2, start=time(12), end=time(14), is_active=False),
            ],
        ),
    )

    assert [slot.id for slot in response.items] == [1]


@pytest.mark.asyncio
async def test_get_time_slots_returns_cached_response() -> None:
    redis_service = FakeRedisService()
    repository = FakeDeliveryTimeSlotRepository()
    query = DeliveryTimeSlotsQueryParams(date=date.today() + timedelta(days=1), delivery_type="delivery")
    cached_response = DeliveryTimeSlotsResponse(date=query.date, delivery_type="delivery", items=[])
    from source.utils.query_hash import build_query_hash

    redis_service.values[f"delivery:time_slots:{build_query_hash(query.model_dump())}"] = cached_response.model_dump_json()

    response = await execute_get_time_slots(
        redis_service=redis_service,
        delivery_time_slot_repository=repository,
        query=query,
    )

    assert response == cached_response
    assert repository.get_by_day_calls == 0


@pytest.mark.asyncio
async def test_invalidate_time_slots_deletes_cache() -> None:
    redis_service = FakeRedisService()
    redis_service.values["delivery:time_slots:abc"] = "{}"

    await DeliveryCacheService().invalidate_time_slots(redis_service=redis_service)

    assert redis_service.deleted == ["delivery:time_slots:abc"]
