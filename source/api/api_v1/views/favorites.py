from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.db.models.user import User
from source.errors.auth import InactiveUserError
from source.repositories.favorite import FavoriteRepository
from source.schemas.pydantic.favorite import FavoritesQueryParams, FavoritesResponse
from source.services.favorite import FavoriteService
from source.services.favorite_cache import FavoriteCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["favorites"])


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
