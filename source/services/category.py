from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.repositories.category import CategoryRepository
from source.schemas.pydantic.category import (
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


class CategoryService:
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

        root_category = None
        if query.root_id is not None:
            root_category = await category_repository.get_active_by_id(
                session=session,
                category_id=query.root_id,
            )
            if root_category is None:
                raise CategoryNotFoundError

        categories = await category_repository.get_active_all(session=session)
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
