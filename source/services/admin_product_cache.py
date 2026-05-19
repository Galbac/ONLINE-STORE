from source.schemas.pydantic.admin_product import AdminProductListResponse
from source.services.redis import RedisService


class AdminProductCacheService:
    def _list_key(self, *, query_hash: str) -> str:
        return f"admin:products:list:{query_hash}"

    async def get_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> AdminProductListResponse | None:
        cached_products = await redis_service.get(self._list_key(query_hash=query_hash))
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return AdminProductListResponse.model_validate_json(cached_products)

    async def set_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminProductListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._list_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_list(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:products:list:*")
