from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.db.models.user import User
from source.repositories.loyalty import LoyaltyRepository
from source.schemas.pydantic.loyalty import LoyaltyResponse
from source.schemas.pydantic.telegram import TelegramConnectResponse, TelegramStatusResponse
from source.services.loyalty import LoyaltyService
from source.services.redis import RedisService
from source.services.telegram_connect import TelegramConnectService

router = APIRouter(tags=["loyalty-and-telegram"])


@router.get("/profile/loyalty", response_model=LoyaltyResponse, status_code=status.HTTP_200_OK)
@inject
async def get_my_loyalty(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    loyalty_repository: FromDishka[LoyaltyRepository] = None,
    loyalty_service: FromDishka[LoyaltyService] = None,
) -> LoyaltyResponse:
    return await loyalty_service.get_loyalty_info(
        session=session,
        loyalty_repository=loyalty_repository,
        user=current_user,
    )


@router.post("/profile/telegram/connect", response_model=TelegramConnectResponse, status_code=status.HTTP_200_OK)
@inject
async def connect_telegram(
    current_user: User = Depends(get_current_user),
    redis_service: FromDishka[RedisService] = None,
    telegram_connect_service: FromDishka[TelegramConnectService] = None,
) -> TelegramConnectResponse:
    return await telegram_connect_service.create_connect_token(
        redis_service=redis_service,
        user=current_user,
    )


@router.get("/profile/telegram/status", response_model=TelegramStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def get_telegram_status(
    current_user: User = Depends(get_current_user),
    telegram_connect_service: FromDishka[TelegramConnectService] = None,
) -> TelegramStatusResponse:
    return await telegram_connect_service.get_status(user=current_user)
