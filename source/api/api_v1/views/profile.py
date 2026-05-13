from datetime import date

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    AddressAccessDeniedError,
    AddressActiveOrderExistsError,
    AddressNotFoundError,
    CurrentUserNotFoundError,
    EmptyUserProfileUpdateError,
    InactiveUserError,
    UserAddressesLimitExceededError,
)
from source.repositories.address import AddressRepository
from source.repositories.order import OrderRepository
from source.repositories.user import UserRepository
from source.schemas.pydantic.auth import MessageResponse
from source.schemas.pydantic.profile import (
    AddressCreateRequest,
    AddressListQueryParams,
    AddressListResponse,
    AddressResponse,
    AddressUpdateRequest,
    ProfileOrderListQueryParams,
    ProfileOrderListResponse,
    ProfileSummaryResponse,
)
from source.services.profile import ProfileService
from source.services.profile_cache import ProfileCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["profile"])


@router.get(
    "/profile/orders",
    response_model=ProfileOrderListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверные query params.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован или удалён.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def get_profile_orders(
    current_user: User = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status", max_length=50),
    payment_status: str | None = Query(default=None, max_length=50),
    delivery_type: str | None = Query(default=None, pattern="^(delivery|pickup)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    profile_service: FromDishka[ProfileService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    user_repository: FromDishka[UserRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> ProfileOrderListResponse:
    try:
        return await profile_service.get_user_orders(
            session=session,
            redis_service=redis_service,
            profile_cache_service=profile_cache_service,
            user_repository=user_repository,
            order_repository=order_repository,
            user_id=current_user.id,
            query=ProfileOrderListQueryParams(
                status=status_filter,
                payment_status=payment_status,
                delivery_type=delivery_type,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            ),
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


@router.post(
    "/profile/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверные входные данные.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован или удалён.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Превышен лимит адресов.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def create_profile_address(
    body: AddressCreateRequest,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    profile_service: FromDishka[ProfileService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    user_repository: FromDishka[UserRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
) -> AddressResponse:
    try:
        response = await profile_service.create_address(
            session=session,
            redis_service=redis_service,
            profile_cache_service=profile_cache_service,
            user_repository=user_repository,
            address_repository=address_repository,
            user_id=current_user.id,
            data=body,
        )
        await commiter.commit()
        return response
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
            detail="Пользователь заблокирован или удалён",
        ) from error


@router.delete(
    "/profile/addresses/{address_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован, удалён или адрес принадлежит другому пользователю.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Адрес не найден.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Адрес используется в активном заказе.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def delete_profile_address(
    address_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    profile_service: FromDishka[ProfileService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    user_repository: FromDishka[UserRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> MessageResponse:
    try:
        await profile_service.delete_address(
            session=session,
            redis_service=redis_service,
            profile_cache_service=profile_cache_service,
            user_repository=user_repository,
            address_repository=address_repository,
            order_repository=order_repository,
            user_id=current_user.id,
            address_id=address_id,
        )
        await commiter.commit()
        return MessageResponse(message="Адрес успешно удалён")
    except CurrentUserNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        ) from error
    except AddressNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Адрес не найден",
        ) from error
    except AddressAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Адрес принадлежит другому пользователю",
        ) from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или удалён",
        ) from error
    except AddressActiveOrderExistsError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Адрес используется в активном заказе",
        ) from error
    except UserAddressesLimitExceededError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Превышен лимит адресов",
        ) from error


@router.patch(
    "/profile/addresses/{address_id}",
    response_model=AddressResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверные входные данные или не передано ни одного поля.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован, удалён или адрес принадлежит другому пользователю.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Адрес не найден.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def update_profile_address(
    address_id: int,
    body: AddressUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    profile_service: FromDishka[ProfileService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    user_repository: FromDishka[UserRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
) -> AddressResponse:
    try:
        response = await profile_service.update_address(
            session=session,
            redis_service=redis_service,
            profile_cache_service=profile_cache_service,
            user_repository=user_repository,
            address_repository=address_repository,
            user_id=current_user.id,
            address_id=address_id,
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
    except AddressNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Адрес не найден",
        ) from error
    except AddressAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Адрес принадлежит другому пользователю",
        ) from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или удалён",
        ) from error


@router.get(
    "/profile/addresses",
    response_model=AddressListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Пользователь не авторизован или access_token недействителен.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Пользователь заблокирован или удалён.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера.",
        },
    },
)
@inject
async def get_profile_addresses(
    current_user: User = Depends(get_current_user),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    profile_service: FromDishka[ProfileService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    user_repository: FromDishka[UserRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
) -> AddressListResponse:
    try:
        return await profile_service.get_user_addresses(
            session=session,
            redis_service=redis_service,
            profile_cache_service=profile_cache_service,
            user_repository=user_repository,
            address_repository=address_repository,
            user_id=current_user.id,
            query=AddressListQueryParams(
                include_deleted=include_deleted,
                limit=limit,
                offset=offset,
            ),
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
