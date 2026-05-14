from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.repositories.category import CategoryRepository
from source.schemas.pydantic.category import CategoryListQueryParams, CategoryListResponse
from source.services.category_cache import CategoryCacheService
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash


class CategoryService:
    async def get_categories(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        category_cache_service: CategoryCacheService,
        category_repository: CategoryRepository,
        query: CategoryListQueryParams,
    ) -> CategoryListResponse:
        query_hash = build_query_hash(query.model_dump())
        cached_categories = await category_cache_service.get_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_categories is not None:
            return cached_categories

        items = await category_repository.get_active_list(session=session, query=query)
        total = await category_repository.count_active(session=session, query=query)
        response = CategoryListResponse(
            items=items,
            total=total,
            limit=query.limit,
            offset=query.offset,
        )
        await category_cache_service.set_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.categories.cache_ttl_seconds,
        )
        return response
