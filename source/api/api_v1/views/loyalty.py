from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.db.models.user import User
from source.repositories.loyalty import LoyaltyRepository
from source.repositories.settings import SettingsRepository
from source.schemas.pydantic.loyalty import LoyaltyResponse
from source.schemas.pydantic.referral import ReferralResponse
from source.schemas.pydantic.telegram import TelegramConnectResponse, TelegramStatusResponse
from source.services.loyalty import LoyaltyService
from source.services.redis import RedisService
from source.services.telegram_connect import TelegramConnectService
from fastapi import HTTPException

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


@router.get("/profile/referral", response_model=ReferralResponse, status_code=status.HTTP_200_OK)
@inject
async def get_my_referral(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    settings_repository: FromDishka[SettingsRepository] = None,
) -> ReferralResponse:
    if settings_repository is not None:
        store_settings, _ = await settings_repository.get_or_create_default(session=session)
        if not store_settings.referral_program_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Реферальная программа временно отключена администратором")

    # Deterministic friendly referral code based on user id
    code_number = (current_user.id * 7919) % 90000 + 10000
    ref_code = f"REF-{code_number}"
    return ReferralResponse(
        code=ref_code,
        link=f"https://grocerystore.ru/register?ref={ref_code}",
        reward_amount=500,
        invited_count=0,
        earned_points=0,
    )
