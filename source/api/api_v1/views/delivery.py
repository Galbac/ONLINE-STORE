from datetime import date

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Body, Header, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import resolve_current_user
from source.errors.delivery import (
    DeliveryAddressAccessDeniedError,
    DeliveryDateInPastError,
    DeliveryAddressNotFoundError,
    DeliveryDisabledError,
    DeliveryMinOrderAmountError,
    PickupDisabledError,
    PickupPointInactiveError,
    PickupPointNotFoundError,
)
from source.repositories.address import AddressRepository
from source.repositories.delivery_settings import DeliverySettingsRepository
from source.repositories.delivery_time_slot import DeliveryTimeSlotRepository
from source.repositories.delivery_zone import DeliveryZoneRepository
from source.repositories.order import OrderRepository
from source.repositories.pickup_point import PickupPointRepository
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
from source.services.redis import RedisService

router = APIRouter(tags=["delivery"])


@router.get(
    "/delivery/options",
    response_model=DeliveryOptionsResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_delivery_options(
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    delivery_service: FromDishka[DeliveryService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    delivery_settings_repository: FromDishka[DeliverySettingsRepository] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
) -> DeliveryOptionsResponse:
    try:
        return await delivery_service.get_options(
            session=session,
            redis_service=redis_service,
            delivery_cache_service=delivery_cache_service,
            delivery_settings_repository=delivery_settings_repository,
            pickup_point_repository=pickup_point_repository,
        )
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get(
    "/delivery/pickup-points",
    response_model=PickupPointListResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_pickup_points(
    city: str | None = Query(default=None, max_length=100),
    only_active: bool = True,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    delivery_service: FromDishka[DeliveryService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
) -> PickupPointListResponse:
    try:
        query = PickupPointListQueryParams(
            city=city,
            only_active=only_active,
            limit=limit,
            offset=offset,
        )
        return await delivery_service.get_pickup_points(
            session=session,
            redis_service=redis_service,
            delivery_cache_service=delivery_cache_service,
            pickup_point_repository=pickup_point_repository,
            query=query,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get(
    "/delivery/pickup-points/{point_id}",
    response_model=PickupPointDetailResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_pickup_point(
    point_id: int,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    delivery_service: FromDishka[DeliveryService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
) -> PickupPointDetailResponse:
    if point_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный point_id")
    try:
        return await delivery_service.get_pickup_point_by_id(
            session=session,
            redis_service=redis_service,
            delivery_cache_service=delivery_cache_service,
            pickup_point_repository=pickup_point_repository,
            point_id=point_id,
        )
    except (PickupPointNotFoundError, PickupPointInactiveError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Точка самовывоза не найдена") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get(
    "/delivery/time-slots",
    response_model=DeliveryTimeSlotsResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_delivery_time_slots(
    date_: date = Query(alias="date"),
    delivery_type: str = Query(...),
    pickup_point_id: int | None = Query(default=None, gt=0),
    address_id: int | None = Query(default=None, gt=0),
    city: str | None = Query(default=None, max_length=100),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    delivery_time_slot_service: FromDishka[DeliveryTimeSlotService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    delivery_settings_repository: FromDishka[DeliverySettingsRepository] = None,
    delivery_time_slot_repository: FromDishka[DeliveryTimeSlotRepository] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> DeliveryTimeSlotsResponse:
    try:
        query = DeliveryTimeSlotsQueryParams(
            date=date_,
            delivery_type=delivery_type,
            pickup_point_id=pickup_point_id,
            address_id=address_id,
            city=city,
        )
        return await delivery_time_slot_service.get_available_slots(
            session=session,
            redis_service=redis_service,
            delivery_cache_service=delivery_cache_service,
            delivery_settings_repository=delivery_settings_repository,
            delivery_time_slot_repository=delivery_time_slot_repository,
            pickup_point_repository=pickup_point_repository,
            order_repository=order_repository,
            query=query,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except DeliveryDateInPastError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date не должна быть в прошлом") from error
    except PickupPointNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Точка самовывоза не найдена") from error
    except DeliveryDisabledError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Доставка отключена") from error
    except PickupDisabledError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Самовывоз отключён") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.post(
    "/delivery/calculate",
    response_model=DeliveryCalculateResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные входные данные или сумма меньше минимальной."},
        status.HTTP_401_UNAUTHORIZED: {"description": "address_id требует авторизации."},
        status.HTTP_403_FORBIDDEN: {"description": "Адрес принадлежит другому пользователю."},
        status.HTTP_404_NOT_FOUND: {"description": "Адрес не найден."},
        status.HTTP_409_CONFLICT: {"description": "Доставка отключена."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def calculate_delivery(
    body: dict = Body(...),
    authorization: str | None = Header(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    delivery_service: FromDishka[DeliveryService] = None,
    delivery_zone_service: FromDishka[DeliveryZoneService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    delivery_settings_repository: FromDishka[DeliverySettingsRepository] = None,
    delivery_zone_repository: FromDishka[DeliveryZoneRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
) -> DeliveryCalculateResponse:
    try:
        data = DeliveryCalculateRequest.model_validate(body)
        current_user = None
        if data.address_id is not None:
            current_user = await resolve_current_user(
                authorization=authorization,
                session=session,
                redis_service=redis_service,
            )
        return await delivery_service.calculate(
            session=session,
            redis_service=redis_service,
            delivery_cache_service=delivery_cache_service,
            delivery_settings_repository=delivery_settings_repository,
            delivery_zone_service=delivery_zone_service,
            delivery_zone_repository=delivery_zone_repository,
            address_repository=address_repository,
            user_id=current_user.id if current_user is not None else None,
            data=data,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные входные данные") from error
    except DeliveryMinOrderAmountError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сумма заказа меньше минимальной") from error
    except DeliveryAddressAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Адрес принадлежит другому пользователю") from error
    except DeliveryAddressNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Адрес не найден") from error
    except DeliveryDisabledError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Доставка отключена") from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error
