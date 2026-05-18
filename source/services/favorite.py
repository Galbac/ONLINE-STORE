from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.auth import InactiveUserError
from source.repositories.favorite import FavoriteRepository
from source.schemas.pydantic.favorite import FavoritesQueryParams, FavoritesResponse
from source.services.favorite_cache import FavoriteCacheService
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash


class FavoriteService:
    async def get_favorites(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        favorite_cache_service: FavoriteCacheService,
        favorite_repository: FavoriteRepository,
        user,
        query: FavoritesQueryParams,
    ) -> FavoritesResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        query_hash = build_query_hash(query.model_dump())
        cached = await favorite_cache_service.get(redis_service=redis_service, user_id=user.id, query_hash=query_hash)
        if cached is not None:
            return cached

        items = await favorite_repository.get_by_user_id(session=session, user_id=user.id, query=query)
        total = await favorite_repository.count_by_user_id(session=session, user_id=user.id)
        response = FavoritesResponse.build(items=items, total=total, page=query.page, limit=query.limit)
        await favorite_cache_service.set(
            redis_service=redis_service,
            user_id=user.id,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.favorites.cache_ttl_seconds,
        )
        return response
