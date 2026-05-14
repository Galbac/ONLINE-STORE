from source.schemas.pydantic.category import CategoryListResponse, CategoryTreeResponse
from source.services.redis import RedisService


class CategoryCacheService:
    def _list_key(self, query_hash: str) -> str:
        return f"categories:list:{query_hash}"

    def _tree_key(self, query_hash: str) -> str:
        return f"categories:tree:{query_hash}"

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

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("categories:list:*")
        await redis_service.delete_by_pattern("categories:tree:*")
        await redis_service.delete_by_pattern("categories:detail:*")
        await redis_service.delete_by_pattern("categories:slug:*")
