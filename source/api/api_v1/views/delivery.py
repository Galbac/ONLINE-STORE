from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.repositories.delivery_settings import DeliverySettingsRepository
from source.repositories.pickup_point import PickupPointRepository
from source.schemas.pydantic.delivery import DeliveryOptionsResponse
from source.services.delivery import DeliveryService
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
