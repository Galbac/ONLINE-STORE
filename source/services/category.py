from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.repositories.category import CategoryRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.category import (
    CategoryBreadcrumbResponse,
    CategoryDetailQueryParams,
    CategoryDetailResponse,
    CategoryListQueryParams,
    CategoryListResponse,
    CategoryShortResponse,
    CategoryTreeItemResponse,
    CategoryTreeQueryParams,
    CategoryTreeResponse,
)
from source.services.category_cache import CategoryCacheService
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.slug import normalize_slug


class CategoryService:
    async def get_category_by_slug(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        category_cache_service: CategoryCacheService,
        category_repository: CategoryRepository,
        product_repository: ProductRepository,
        slug: str,
        query: CategoryDetailQueryParams,
    ) -> CategoryDetailResponse:
        normalized_slug = normalize_slug(slug)
        query_hash = build_query_hash(query.model_dump())
        cached_category = await category_cache_service.get_by_slug(
            redis_service=redis_service,
            slug=normalized_slug,
            query_hash=query_hash,
        )
        if cached_category is not None:
            return cached_category

        category = await category_repository.get_active_by_slug(session=session, slug=normalized_slug)
        if category is None:
            raise CategoryNotFoundError

        response = await self._build_detail_response(
            session=session,
            category_repository=category_repository,
            product_repository=product_repository,
            category=category,
            query=query,
        )
        await category_cache_service.set_by_slug(
            redis_service=redis_service,
            slug=normalized_slug,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.categories.slug_cache_ttl_seconds,
        )
        return response

    async def get_category_by_id(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        category_cache_service: CategoryCacheService,
        category_repository: CategoryRepository,
        product_repository: ProductRepository,
        category_id: int,
        query: CategoryDetailQueryParams,
    ) -> CategoryDetailResponse:
        query_hash = build_query_hash(query.model_dump())
        cached_category = await category_cache_service.get_detail(
            redis_service=redis_service,
            category_id=category_id,
            query_hash=query_hash,
        )
        if cached_category is not None:
            return cached_category

        category = await category_repository.get_active_by_id(session=session, category_id=category_id)
        if category is None:
            raise CategoryNotFoundError

        response = await self._build_detail_response(
            session=session,
            category_repository=category_repository,
            product_repository=product_repository,
            category=category,
            query=query,
        )
        await category_cache_service.set_detail(
            redis_service=redis_service,
            category_id=category.id,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.categories.detail_cache_ttl_seconds,
        )
        return response

    async def _build_detail_response(
        self,
        *,
        session: AsyncSession,
        category_repository: CategoryRepository,
        product_repository: ProductRepository,
        category: CategoryDetailResponse,
        query: CategoryDetailQueryParams,
    ) -> CategoryDetailResponse:
        products_count = None
        if query.with_products_count:
            products_count = await product_repository.count_active_by_category_id(
                session=session,
                category_id=category.id,
            )

        response = category.model_copy(
            update={
                "products_count": products_count,
                "children": await self.get_children(
                    session=session,
                    category_repository=category_repository,
                    category_id=category.id,
                    with_products_count=query.with_products_count,
                ) if query.with_children else None,
                "breadcrumbs": await self.get_breadcrumbs(
                    session=session,
                    category_repository=category_repository,
                    category_id=category.id,
                ) if query.with_breadcrumbs else None,
            },
        )
        return response

    async def get_children(
        self,
        *,
        session: AsyncSession,
        category_repository: CategoryRepository,
        category_id: int,
        with_products_count: bool,
    ) -> list[CategoryShortResponse]:
        children = await category_repository.get_active_children(session=session, parent_id=category_id)
        if with_products_count:
            return children
        return [
            child.model_copy(update={"products_count": None})
            for child in children
        ]

    async def get_breadcrumbs(
        self,
        *,
        session: AsyncSession,
        category_repository: CategoryRepository,
        category_id: int,
    ) -> list[CategoryBreadcrumbResponse]:
        return await category_repository.get_parent_chain(session=session, category_id=category_id)

    async def get_category_tree(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        category_cache_service: CategoryCacheService,
        category_repository: CategoryRepository,
        query: CategoryTreeQueryParams,
    ) -> CategoryTreeResponse:
        query_hash = build_query_hash(query.model_dump())
        cached_tree = await category_cache_service.get_tree(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_tree is not None:
            return cached_tree

        root_category_id = None
        if query.root_id is not None:
            root_category = await category_repository.get_active_by_id(
                session=session,
                category_id=query.root_id,
            )
            if root_category is None:
                raise CategoryNotFoundError
            root_category_id = root_category.id

        categories = await category_repository.get_active_all(session=session)
        root_category = None
        if root_category_id is not None:
            root_category = next((category for category in categories if category.id == root_category_id), None)
        response = CategoryTreeResponse(
            items=self.build_tree(
                categories=categories,
                query=query,
                root_category=root_category,
            ),
        )
        await category_cache_service.set_tree(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.categories.tree_cache_ttl_seconds,
        )
        return response

    def build_tree(
        self,
        *,
        categories: list[CategoryShortResponse],
        query: CategoryTreeQueryParams,
        root_category: CategoryShortResponse | None = None,
    ) -> list[CategoryTreeItemResponse]:
        children_by_parent_id: dict[int | None, list[CategoryShortResponse]] = {}
        for category in sorted(categories, key=lambda item: (item.sort_order, item.name)):
            children_by_parent_id.setdefault(category.parent_id, []).append(category)

        def build_node(category: CategoryShortResponse, depth: int) -> CategoryTreeItemResponse | None:
            children = []
            if depth < query.max_depth:
                children = [
                    child_node
                    for child in children_by_parent_id.get(category.id, [])
                    if (child_node := build_node(child, depth + 1)) is not None
                ]
            if not query.include_empty and category.products_count <= 0 and not children:
                return None
            return CategoryTreeItemResponse(
                id=category.id,
                name=category.name,
                slug=category.slug,
                parent_id=category.parent_id,
                image_url=category.image_url,
                sort_order=category.sort_order,
                products_count=category.products_count if query.with_products_count else None,
                children=children,
            )

        root_categories = [root_category] if root_category is not None else children_by_parent_id.get(None, [])
        return [
            node
            for category in root_categories
            if (node := build_node(category, 1)) is not None
        ]

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
