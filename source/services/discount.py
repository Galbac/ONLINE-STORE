from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.product_stock import ProductStock
from source.repositories.discount import DiscountRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.discount import (
    ActiveDiscountsQueryParams,
    ActiveDiscountsResponse,
    DiscountProductsQueryParams,
    DiscountProductsResponse,
)
from source.services.discount_cache import DiscountCacheService
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.product import build_stock_display
from source.schemas.pydantic.product import ProductShortResponse


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
        items = await self._attach_store_stock(session=session, items=items, store_id=query.store_id)
        total = await product_repository.count_discounted_products(session=session, query=query)
        response = DiscountProductsResponse.build(items=items, total=total, page=query.page, limit=query.limit)
        await discount_cache_service.set_products(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.discounts.products_cache_ttl_seconds,
        )
        return response

    async def _attach_store_stock(
        self,
        *,
        session: AsyncSession,
        items: list[ProductShortResponse],
        store_id: int | None,
    ) -> list[ProductShortResponse]:
        if store_id is None or not items:
            return items
        result = await session.execute(
            select(ProductStock.product_id, ProductStock.stock_quantity).where(
                ProductStock.product_id.in_([item.id for item in items]),
                ProductStock.pickup_point_id == store_id,
            ),
        )
        quantities = {product_id: quantity for product_id, quantity in result.all()}
        updated_items = []
        for item in items:
            quantity = quantities.get(item.id, 0)
            available = quantity > 0
            updated_items.append(
                item.model_copy(
                    update={
                        "store_stock_quantity": quantity,
                        "store_is_available": available,
                        "is_available": available,
                        "stock_display": build_stock_display(is_available=available, stock_quantity=quantity),
                    },
                ),
            )
        return updated_items
