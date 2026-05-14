from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.errors.product import ProductNotFoundError
from source.repositories.category import CategoryRepository
from source.repositories.product import ProductRepository
from source.repositories.product_image import ProductImageRepository
from source.schemas.pydantic.product import (
    ProductBreadcrumbResponse,
    ProductDetailQueryParams,
    ProductDetailResponse,
    ProductListQueryParams,
    ProductListResponse,
    ProductPopularQueryParams,
    ProductPopularResponse,
    ProductSearchQueryParams,
    ProductSearchResponse,
)
from source.services.product_cache import ProductCacheService
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query
from source.utils.slug import normalize_slug


class ProductService:
    async def get_product_by_id(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        product_cache_service: ProductCacheService,
        product_repository: ProductRepository,
        product_image_repository: ProductImageRepository,
        category_repository: CategoryRepository,
        product_id: int,
        query: ProductDetailQueryParams,
    ) -> ProductDetailResponse:
        query_hash = build_query_hash(query.model_dump())
        cached_product = await product_cache_service.get_detail(
            redis_service=redis_service,
            product_id=product_id,
            query_hash=query_hash,
        )
        if cached_product is not None:
            return cached_product

        product = await product_repository.get_active_by_id(session=session, product_id=product_id)
        if product is None:
            raise ProductNotFoundError

        response = await self._build_product_detail_response(
            session=session,
            product=product,
            query=query,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            category_repository=category_repository,
        )
        await product_cache_service.set_detail(
            redis_service=redis_service,
            product_id=product.id,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.products.detail_cache_ttl_seconds,
        )
        return response

    async def get_product_by_slug(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        product_cache_service: ProductCacheService,
        product_repository: ProductRepository,
        product_image_repository: ProductImageRepository,
        category_repository: CategoryRepository,
        slug: str,
        query: ProductDetailQueryParams,
    ) -> ProductDetailResponse:
        normalized_slug = normalize_slug(slug)
        query_hash = build_query_hash(query.model_dump())
        cached_product = await product_cache_service.get_by_slug(
            redis_service=redis_service,
            slug=normalized_slug,
            query_hash=query_hash,
        )
        if cached_product is not None:
            return cached_product

        product = await product_repository.get_active_by_slug(session=session, slug=normalized_slug)
        if product is None:
            raise ProductNotFoundError

        response = await self._build_product_detail_response(
            session=session,
            product=product,
            query=query,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            category_repository=category_repository,
        )
        await product_cache_service.set_by_slug(
            redis_service=redis_service,
            slug=normalized_slug,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.products.slug_cache_ttl_seconds,
        )
        return response

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

    async def search_products(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        product_cache_service: ProductCacheService,
        product_repository: ProductRepository,
        category_repository: CategoryRepository,
        query: ProductSearchQueryParams,
    ) -> ProductSearchResponse:
        normalized_query = query.model_copy(update={"q": normalize_search_query(query.q)})
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_products = await product_cache_service.get_search(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_products is not None:
            return cached_products

        category_ids = await self._resolve_category_ids_by_id(
            session=session,
            category_repository=category_repository,
            category_id=normalized_query.category_id,
        )
        items = await product_repository.search_active(
            session=session,
            query=normalized_query,
            category_ids=category_ids,
        )
        total = await product_repository.count_search_active(
            session=session,
            query=normalized_query,
            category_ids=category_ids,
        )
        response = ProductSearchResponse.build(
            query=normalized_query.q,
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await product_cache_service.set_search(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.products.search_cache_ttl_seconds,
        )
        return response

    async def get_popular_products(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        product_cache_service: ProductCacheService,
        product_repository: ProductRepository,
        category_repository: CategoryRepository,
        query: ProductPopularQueryParams,
    ) -> ProductPopularResponse:
        query_hash = build_query_hash(query.model_dump())
        cached_products = await product_cache_service.get_popular(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_products is not None:
            return cached_products

        category_ids = await self._resolve_category_ids_by_id(
            session=session,
            category_repository=category_repository,
            category_id=query.category_id,
        )
        items = await product_repository.get_popular_active(
            session=session,
            query=query,
            category_ids=category_ids,
        )
        response = ProductPopularResponse(items=items, total=len(items))
        await product_cache_service.set_popular(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.products.popular_cache_ttl_seconds,
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

    async def _resolve_category_ids_by_id(
        self,
        *,
        session: AsyncSession,
        category_repository: CategoryRepository,
        category_id: int | None,
    ) -> set[int] | None:
        if category_id is None:
            return None

        category = await category_repository.get_active_by_id(session=session, category_id=category_id)
        if category is None:
            raise CategoryNotFoundError

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

    async def _build_product_detail_response(
        self,
        *,
        session: AsyncSession,
        product: ProductDetailResponse,
        query: ProductDetailQueryParams,
        product_repository: ProductRepository,
        product_image_repository: ProductImageRepository,
        category_repository: CategoryRepository,
    ) -> ProductDetailResponse:
        breadcrumbs = None
        if query.with_breadcrumbs and product.category is not None:
            breadcrumbs = [
                ProductBreadcrumbResponse(
                    id=breadcrumb.id,
                    name=breadcrumb.name,
                    slug=breadcrumb.slug,
                )
                for breadcrumb in await category_repository.get_parent_chain(
                    session=session,
                    category_id=product.category.id,
                )
            ]

        similar = None
        if query.with_similar:
            similar = await product_repository.get_similar_active(
                session=session,
                product_id=product.id,
                category_id=product.category.id if product.category is not None else None,
            )

        return product.model_copy(
            update={
                "images": await product_image_repository.get_by_product_id(
                    session=session,
                    product_id=product.id,
                ),
                "breadcrumbs": breadcrumbs,
                "similar": similar,
            },
        )
