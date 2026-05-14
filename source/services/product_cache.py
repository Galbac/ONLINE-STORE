from source.schemas.pydantic.product import ProductListResponse
from source.services.redis import RedisService


class ProductCacheService:
    def _list_key(self, query_hash: str) -> str:
        return f"products:list:{query_hash}"

    async def get_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> ProductListResponse | None:
        cached_products = await redis_service.get(self._list_key(query_hash))
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return ProductListResponse.model_validate_json(cached_products)

    async def set_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: ProductListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._list_key(query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:detail:*")
        await redis_service.delete_by_pattern("products:slug:*")
        await redis_service.delete_by_pattern("products:search:*")
        await redis_service.delete_by_pattern("products:popular:*")
        await redis_service.delete_by_pattern("products:discounted:*")
        await redis_service.delete_by_pattern("products:new:*")
