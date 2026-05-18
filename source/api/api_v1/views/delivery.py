from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import resolve_current_user
from source.errors.delivery import (
    DeliveryAddressAccessDeniedError,
    DeliveryAddressNotFoundError,
    DeliveryDisabledError,
    DeliveryMinOrderAmountError,
)
from source.repositories.address import AddressRepository
from source.repositories.delivery_settings import DeliverySettingsRepository
from source.repositories.delivery_zone import DeliveryZoneRepository
from source.repositories.pickup_point import PickupPointRepository
from source.schemas.pydantic.delivery import DeliveryCalculateRequest, DeliveryCalculateResponse, DeliveryOptionsResponse
from source.services.delivery import DeliveryService, DeliveryZoneService
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
