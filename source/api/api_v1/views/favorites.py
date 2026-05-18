from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.db.models.user import User
from source.common.commiter import Commiter
from source.errors.auth import InactiveUserError
from source.errors.favorite import FavoriteProductNotFoundError, FavoriteProductUnavailableError
from source.repositories.favorite import FavoriteRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.favorite import FavoriteActionResponse, FavoritesQueryParams, FavoritesResponse
from source.services.favorite import FavoriteService
from source.services.favorite_cache import FavoriteCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["favorites"])


@router.delete(
    "/favorites/{product_id}",
    response_model=FavoriteActionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверный product_id."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def remove_from_favorites(
    product_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    favorite_service: FromDishka[FavoriteService] = None,
    favorite_cache_service: FromDishka[FavoriteCacheService] = None,
    favorite_repository: FromDishka[FavoriteRepository] = None,
) -> FavoriteActionResponse:
    if product_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный product_id")
    try:
        response = await favorite_service.remove_from_favorites(
            session=session,
            redis_service=redis_service,
            favorite_cache_service=favorite_cache_service,
            favorite_repository=favorite_repository,
            user=current_user,
            product_id=product_id,
        )
        await commiter.commit()
        return response
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.post(
    "/favorites/{product_id}",
    response_model=FavoriteActionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверный product_id."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован."},
        status.HTTP_404_NOT_FOUND: {"description": "Товар не найден."},
        status.HTTP_409_CONFLICT: {"description": "Товар недоступен для добавления в избранное."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def add_to_favorites(
    product_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    favorite_service: FromDishka[FavoriteService] = None,
    favorite_cache_service: FromDishka[FavoriteCacheService] = None,
    favorite_repository: FromDishka[FavoriteRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> FavoriteActionResponse:
    if product_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный product_id")
    try:
        response = await favorite_service.add_to_favorites(
            session=session,
            redis_service=redis_service,
            favorite_cache_service=favorite_cache_service,
            favorite_repository=favorite_repository,
            product_repository=product_repository,
            user=current_user,
            product_id=product_id,
        )
        await commiter.commit()
        return response
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except FavoriteProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except FavoriteProductUnavailableError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Товар недоступен") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get("/favorites", response_model=FavoritesResponse, response_model_exclude_none=True, status_code=status.HTTP_200_OK)
@inject
async def get_favorites(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    favorite_service: FromDishka[FavoriteService] = None,
    favorite_cache_service: FromDishka[FavoriteCacheService] = None,
    favorite_repository: FromDishka[FavoriteRepository] = None,
) -> FavoritesResponse:
    try:
        query = FavoritesQueryParams(page=page, limit=limit)
        return await favorite_service.get_favorites(
            session=session,
            redis_service=redis_service,
            favorite_cache_service=favorite_cache_service,
            favorite_repository=favorite_repository,
            user=current_user,
            query=query,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error
