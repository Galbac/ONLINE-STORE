from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.repositories.category import CategoryRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.product import ProductListQueryParams, ProductListResponse
from source.services.product_cache import ProductCacheService
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.slug import normalize_slug


class ProductService:
    async def get_products(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        product_cache_service: ProductCacheService,
        product_repository: ProductRepository,
        category_repository: CategoryRepository,
        query: ProductListQueryParams,
    ) -> ProductListResponse:
        normalized_query = query.model_copy(
            update={
                "category_slug": normalize_slug(query.category_slug) if query.category_slug is not None else None,
            },
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_products = await product_cache_service.get_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_products is not None:
            return cached_products

        category_ids = await self._resolve_category_ids(
            session=session,
            category_repository=category_repository,
            query=normalized_query,
        )
        items = await product_repository.get_active_list(
            session=session,
            query=normalized_query,
            category_ids=category_ids,
        )
        total = await product_repository.count_active(
            session=session,
            query=normalized_query,
            category_ids=category_ids,
        )
        response = ProductListResponse.build(
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await product_cache_service.set_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.products.list_cache_ttl_seconds,
        )
        return response

    async def _resolve_category_ids(
        self,
        *,
        session: AsyncSession,
        category_repository: CategoryRepository,
        query: ProductListQueryParams,
    ) -> set[int] | None:
        category_id = query.category_id
        if category_id is None and query.category_slug is not None:
            category = await category_repository.get_active_by_slug(session=session, slug=query.category_slug)
            if category is None:
                raise CategoryNotFoundError
            category_id = category.id
        elif category_id is not None:
            category = await category_repository.get_active_by_id(session=session, category_id=category_id)
            if category is None:
                raise CategoryNotFoundError

        if category_id is None:
            return None

        categories = await category_repository.get_active_all(session=session)
        category_ids = {category_id}
        pending_ids = [category_id]
        while pending_ids:
            parent_id = pending_ids.pop()
            child_ids = [
                category.id
                for category in categories
                if category.parent_id == parent_id and category.id not in category_ids
            ]
            category_ids.update(child_ids)
            pending_ids.extend(child_ids)
        return category_ids
