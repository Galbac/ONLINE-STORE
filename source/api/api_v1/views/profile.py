from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.db.models.user import User
from source.errors.auth import CurrentUserNotFoundError, InactiveUserError
from source.repositories.address import AddressRepository
from source.repositories.order import OrderRepository
from source.repositories.user import UserRepository
from source.schemas.pydantic.profile import ProfileSummaryResponse
from source.services.profile import ProfileService
from source.services.profile_cache import ProfileCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["profile"])


@router.get(
    "/profile",
    response_model=ProfileSummaryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован или удалён.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Пользователь не найден.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def get_profile_summary(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    profile_service: FromDishka[ProfileService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    user_repository: FromDishka[UserRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> ProfileSummaryResponse:
    try:
        return await profile_service.get_profile_summary(
            session=session,
            redis_service=redis_service,
            profile_cache_service=profile_cache_service,
            user_repository=user_repository,
            address_repository=address_repository,
            order_repository=order_repository,
            user_id=current_user.id,
        )
    except CurrentUserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        ) from error
    except InactiveUserError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или удалён",
        ) from error
