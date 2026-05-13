from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    ActiveOrdersExistError,
    CurrentUserNotFoundError,
    EmptyUserProfileUpdateError,
    InvalidCurrentPasswordError,
    InactiveUserError,
    UserDeleteConfirmationRequiredError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.auth import MessageResponse
from source.schemas.pydantic.user import UserMeDeleteRequest, UserMeResponse, UserMeUpdateRequest
from source.repositories.user import UserRepository
from source.services.auth import AuthService
from source.services.auth_cache import AuthCacheService
from source.services.profile_cache import ProfileCacheService
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
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    user_repository: FromDishka[UserRepository] = None,
) -> UserMeResponse:
    try:
        response = await user_service.update_current_user_profile(
            session=session,
            redis_service=redis_service,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            profile_cache_service=profile_cache_service,
            user_repository=user_repository,
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


@router.delete(
    "/me",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Не подтверждено удаление аккаунта.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Неверный пароль или пользователь уже заблокирован.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "У пользователя есть активные заказы.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def delete_user_me(
    body: UserMeDeleteRequest,
    current_user: User = Depends(get_current_user),
    authorization: str | None = Header(default=None),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    user_service: FromDishka[UserService] = None,
    user_cache_service: FromDishka[UserCacheService] = None,
    auth_cache_service: FromDishka[AuthCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    auth_service: FromDishka[AuthService] = None,
) -> MessageResponse:
    try:
        _, _, access_token = (authorization or "").partition(" ")
        await user_service.delete_current_user_account(
            session=session,
            redis_service=redis_service,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            profile_cache_service=profile_cache_service,
            auth_service=auth_service,
            user_id=current_user.id,
            data=body,
            access_token=access_token or None,
        )
        await commiter.commit()
        return MessageResponse(message="Аккаунт успешно удалён")
    except UserDeleteConfirmationRequiredError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для удаления аккаунта необходимо подтверждение",
        ) from error
    except InvalidCurrentPasswordError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Текущий пароль указан неверно",
        ) from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или неактивен",
        ) from error
    except CurrentUserNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        ) from error
    except ActiveOrdersExistError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя удалить аккаунт, пока есть активные заказы",
        ) from error
