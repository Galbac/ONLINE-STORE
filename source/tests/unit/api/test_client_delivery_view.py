from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.delivery import (
    calculate_delivery,
    get_delivery_options,
    get_delivery_time_slots,
    get_pickup_point,
    get_pickup_points,
)
from source.errors.delivery import (
    DeliveryAddressNotFoundError,
    DeliveryDateInPastError,
    DeliveryMinOrderAmountError,
    PickupPointNotFoundError,
)
from source.schemas.pydantic.delivery import (
    DeliveryCalculateResponse,
    DeliveryOptionItemResponse,
    DeliveryOptionsResponse,
    DeliveryTimeSlotsResponse,
    PickupPointDetailResponse,
    PickupPointListResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


# ---------------------------------------------------------
# GET /delivery/options
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_delivery_options_success():
    service = AsyncMock()
    service.get_options.return_value = DeliveryOptionsResponse(
        delivery=DeliveryOptionItemResponse(
            enabled=True,
            title="Курьерская доставка",
            min_order_amount=Decimal("500.00"),
            base_price=Decimal("150.00"),
        ),
        pickup=DeliveryOptionItemResponse(
            enabled=True,
            title="Самовывоз",
            min_order_amount=Decimal("0.00"),
            base_price=Decimal("0.00"),
        ),
    )

    response = await unwrap(get_delivery_options)(
        session=AsyncMock(),
        redis_service=AsyncMock(),
        delivery_service=service,
        delivery_cache_service=AsyncMock(),
        delivery_settings_repository=AsyncMock(),
        pickup_point_repository=AsyncMock(),
    )

    assert response.delivery.enabled is True
    assert response.pickup.enabled is True


# ---------------------------------------------------------
# GET /delivery/pickup-points
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_pickup_points_success():
    service = AsyncMock()
    service.get_pickup_points.return_value = PickupPointListResponse(
        items=[],
        total=0,
        limit=50,
        offset=0,
    )

    response = await unwrap(get_pickup_points)(
        city=None,
        only_active=True,
        limit=50,
        offset=0,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        delivery_service=service,
        delivery_cache_service=AsyncMock(),
        pickup_point_repository=AsyncMock(),
    )

    assert response.total == 0


# ---------------------------------------------------------
# GET /delivery/pickup-points/{point_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_pickup_point_success():
    service = AsyncMock()
    service.get_pickup_point_by_id.return_value = PickupPointDetailResponse(
        id=1,
        name="Центральный склад",
        address="ул. Ленина, 1",
        city="Кизляр",
        is_active=True,
    )

    response = await unwrap(get_pickup_point)(
        point_id=1,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        delivery_service=service,
        delivery_cache_service=AsyncMock(),
        pickup_point_repository=AsyncMock(),
    )

    assert response.id == 1
    assert response.name == "Центральный склад"


@pytest.mark.asyncio
async def test_get_pickup_point_not_found():
    service = AsyncMock()
    service.get_pickup_point_by_id.side_effect = PickupPointNotFoundError

    with pytest.raises(HTTPException) as exc:
        await unwrap(get_pickup_point)(
            point_id=999,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            delivery_service=service,
            delivery_cache_service=AsyncMock(),
            pickup_point_repository=AsyncMock(),
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------
# GET /delivery/time-slots
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_delivery_time_slots_success():
    service = AsyncMock()
    service.get_available_slots.return_value = DeliveryTimeSlotsResponse(
        date=date(2026, 9, 21),
        delivery_type="delivery",
        items=[],
    )

    response = await unwrap(get_delivery_time_slots)(
        date_=date(2026, 9, 21),
        delivery_type="delivery",
        pickup_point_id=None,
        address_id=None,
        city=None,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        delivery_time_slot_service=service,
        delivery_cache_service=AsyncMock(),
        delivery_settings_repository=AsyncMock(),
        delivery_time_slot_repository=AsyncMock(),
        pickup_point_repository=AsyncMock(),
        order_repository=AsyncMock(),
    )

    assert response.date == date(2026, 9, 21)


@pytest.mark.asyncio
async def test_get_delivery_time_slots_past_date():
    service = AsyncMock()
    service.get_available_slots.side_effect = DeliveryDateInPastError

    with pytest.raises(HTTPException) as exc:
        await unwrap(get_delivery_time_slots)(
            date_=date(2020, 1, 1),
            delivery_type="delivery",
            pickup_point_id=None,
            address_id=None,
            city=None,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            delivery_time_slot_service=service,
            delivery_cache_service=AsyncMock(),
            delivery_settings_repository=AsyncMock(),
            delivery_time_slot_repository=AsyncMock(),
            pickup_point_repository=AsyncMock(),
            order_repository=AsyncMock(),
        )
    assert exc.value.status_code == 400


# ---------------------------------------------------------
# POST /delivery/calculate
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_delivery_success():
    service = AsyncMock()
    service.calculate.return_value = DeliveryCalculateResponse(
        delivery_price=Decimal("150.00"),
        available=True,
        message="Доставка возможна",
    )

    body = {
        "city": "Кизляр",
        "street": "Ленина",
        "house": "10",
        "order_amount": 1000.0,
    }

    response = await unwrap(calculate_delivery)(
        body=body,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        delivery_service=service,
        delivery_zone_service=AsyncMock(),
        delivery_cache_service=AsyncMock(),
        delivery_settings_repository=AsyncMock(),
        delivery_zone_repository=AsyncMock(),
        address_repository=AsyncMock(),
    )

    assert response.delivery_price == Decimal("150.00")
    assert response.available is True


@pytest.mark.asyncio
async def test_calculate_delivery_min_amount_error():
    service = AsyncMock()
    service.calculate.side_effect = DeliveryMinOrderAmountError

    body = {
        "city": "Кизляр",
        "street": "Ленина",
        "house": "10",
        "order_amount": 50.0,
    }

    with pytest.raises(HTTPException) as exc:
        await unwrap(calculate_delivery)(
            body=body,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            delivery_service=service,
            delivery_zone_service=AsyncMock(),
            delivery_cache_service=AsyncMock(),
            delivery_settings_repository=AsyncMock(),
            delivery_zone_repository=AsyncMock(),
            address_repository=AsyncMock(),
        )
    assert exc.value.status_code == 400
    assert "минимальн" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_calculate_delivery_address_not_found():
    service = AsyncMock()
    service.calculate.side_effect = DeliveryAddressNotFoundError

    body = {
        "city": "Несуществующий",
        "street": "Улица",
        "house": "1",
        "order_amount": 1000.0,
    }

    with pytest.raises(HTTPException) as exc:
        await unwrap(calculate_delivery)(
            body=body,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            delivery_service=service,
            delivery_zone_service=AsyncMock(),
            delivery_cache_service=AsyncMock(),
            delivery_settings_repository=AsyncMock(),
            delivery_zone_repository=AsyncMock(),
            address_repository=AsyncMock(),
        )
    assert exc.value.status_code == 404
