from source.schemas.pydantic.admin_category import AdminCategoryListResponse
from source.services.redis import RedisService


class AdminCategoryCacheService:
    def _list_key(self, *, query_hash: str) -> str:
        return f"admin:categories:list:{query_hash}"

    async def get_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> AdminCategoryListResponse | None:
        cached_categories = await redis_service.get(self._list_key(query_hash=query_hash))
        if cached_categories is None:
            return None
        if isinstance(cached_categories, bytes):
            cached_categories = cached_categories.decode("utf-8")
        return AdminCategoryListResponse.model_validate_json(cached_categories)

    async def set_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminCategoryListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._list_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:categories:list:*")
