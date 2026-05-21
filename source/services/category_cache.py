from source.schemas.pydantic.category import CategoryDetailResponse, CategoryListResponse, CategoryTreeResponse
from source.services.redis import RedisService


class CategoryCacheService:
    def _list_key(self, query_hash: str) -> str:
        return f"categories:list:{query_hash}"

    def _tree_key(self, query_hash: str) -> str:
        return f"categories:tree:{query_hash}"

    def _detail_key(self, *, category_id: int, query_hash: str) -> str:
        return f"categories:detail:{category_id}:{query_hash}"

    def _slug_key(self, *, slug: str, query_hash: str) -> str:
        return f"categories:slug:{slug}:{query_hash}"

    async def get_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> CategoryListResponse | None:
        cached_categories = await redis_service.get(self._list_key(query_hash))
        if cached_categories is None:
            return None
        if isinstance(cached_categories, bytes):
            cached_categories = cached_categories.decode("utf-8")
        return CategoryListResponse.model_validate_json(cached_categories)

    async def set_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: CategoryListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._list_key(query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def get_tree(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> CategoryTreeResponse | None:
        cached_tree = await redis_service.get(self._tree_key(query_hash))
        if cached_tree is None:
            return None
        if isinstance(cached_tree, bytes):
            cached_tree = cached_tree.decode("utf-8")
        return CategoryTreeResponse.model_validate_json(cached_tree)

    async def set_tree(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: CategoryTreeResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._tree_key(query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def get_detail(
        self,
        *,
        redis_service: RedisService,
        category_id: int,
        query_hash: str,
    ) -> CategoryDetailResponse | None:
        cached_category = await redis_service.get(
            self._detail_key(category_id=category_id, query_hash=query_hash),
        )
        if cached_category is None:
            return None
        if isinstance(cached_category, bytes):
            cached_category = cached_category.decode("utf-8")
        return CategoryDetailResponse.model_validate_json(cached_category)

    async def set_detail(
        self,
        *,
        redis_service: RedisService,
        category_id: int,
        query_hash: str,
        response: CategoryDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._detail_key(category_id=category_id, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def get_by_slug(
        self,
        *,
        redis_service: RedisService,
        slug: str,
        query_hash: str,
    ) -> CategoryDetailResponse | None:
        cached_category = await redis_service.get(
            self._slug_key(slug=slug, query_hash=query_hash),
        )
        if cached_category is None:
            return None
        if isinstance(cached_category, bytes):
            cached_category = cached_category.decode("utf-8")
        return CategoryDetailResponse.model_validate_json(cached_category)

    async def set_by_slug(
        self,
        *,
        redis_service: RedisService,
        slug: str,
        query_hash: str,
        response: CategoryDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._slug_key(slug=slug, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_category(self, *, redis_service: RedisService, category_id: int, slug: str | None = None) -> None:
        await redis_service.delete_by_pattern(f"categories:detail:{category_id}:*")
        if slug is not None:
            await redis_service.delete_by_pattern(f"categories:slug:{slug}:*")
        await redis_service.delete_by_pattern("categories:list:*")
        await redis_service.delete_by_pattern("categories:tree:*")

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("categories:list:*")
        await redis_service.delete_by_pattern("categories:tree:*")
        await redis_service.delete_by_pattern("categories:detail:*")
        await redis_service.delete_by_pattern("categories:slug:*")

    async def invalidate_tree(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("categories:tree:*")
