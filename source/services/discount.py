from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.repositories.discount import DiscountRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.discount import ActiveDiscountsQueryParams, ActiveDiscountsResponse, DiscountProductsQueryParams, DiscountProductsResponse
from source.services.discount_cache import DiscountCacheService
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash


class DiscountService:
    async def get_active_discounts(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        discount_cache_service: DiscountCacheService,
        discount_repository: DiscountRepository,
        query: ActiveDiscountsQueryParams,
    ) -> ActiveDiscountsResponse:
        query_hash = build_query_hash(query.model_dump())
        cached = await discount_cache_service.get_active(redis_service=redis_service, query_hash=query_hash)
        if cached is not None:
            return cached
        now = datetime.now(settings.tz)
        items = await discount_repository.get_active(session=session, query=query, now=now)
        total = await discount_repository.count_active(session=session, query=query, now=now)
        response = ActiveDiscountsResponse(items=items, total=total, limit=query.limit, offset=query.offset)
        await discount_cache_service.set_active(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.discounts.active_cache_ttl_seconds,
        )
        return response

    async def get_discounted_products(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        discount_cache_service: DiscountCacheService,
        product_repository: ProductRepository,
        query: DiscountProductsQueryParams,
    ) -> DiscountProductsResponse:
        query_hash = build_query_hash(query.model_dump())
        cached = await discount_cache_service.get_products(redis_service=redis_service, query_hash=query_hash)
        if cached is not None:
            return cached
        items = await product_repository.get_discounted_products(session=session, query=query)
        total = await product_repository.count_discounted_products(session=session, query=query)
        response = DiscountProductsResponse.build(items=items, total=total, page=query.page, limit=query.limit)
        await discount_cache_service.set_products(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.discounts.products_cache_ttl_seconds,
        )
        return response
