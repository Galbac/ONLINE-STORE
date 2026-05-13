from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    CurrentUserNotFoundError,
    EmptyUserProfileUpdateError,
    InactiveUserError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.user import UserMeResponse, UserMeUpdateRequest
from source.services.auth_cache import AuthCacheService
from source.services.redis import RedisService
from source.services.user import UserService
from source.services.user_cache import UserCacheService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserMeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован или неактивен.",
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
async def get_user_me(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    user_service: FromDishka[UserService] = None,
    user_cache_service: FromDishka[UserCacheService] = None,
) -> UserMeResponse:
    try:
        return await user_service.get_current_user_profile(
            session=session,
            redis_service=redis_service,
            user_cache_service=user_cache_service,
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
            detail="Пользователь заблокирован или неактивен",
        ) from error


@router.patch(
    "/me",
    response_model=UserMeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверные данные профиля.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован или неактивен.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Пользователь не найден.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Телефон или email уже используются другим пользователем.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def update_user_me(
    body: UserMeUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    user_service: FromDishka[UserService] = None,
    user_cache_service: FromDishka[UserCacheService] = None,
    auth_cache_service: FromDishka[AuthCacheService] = None,
) -> UserMeResponse:
    try:
        response = await user_service.update_current_user_profile(
            session=session,
            redis_service=redis_service,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            user_id=current_user.id,
            data=body,
        )
        await commiter.commit()
        return response
    except EmptyUserProfileUpdateError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не передано ни одного поля для изменения",
        ) from error
    except CurrentUserNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        ) from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или неактивен",
        ) from error
    except UserPhoneAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким телефоном уже существует",
        ) from error
    except UserEmailAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        ) from error
