from source.schemas.pydantic.discount import ActiveDiscountsResponse, DiscountProductsResponse
from source.services.redis import RedisService


class DiscountCacheService:
    def _active_key(self, *, query_hash: str) -> str:
        return f"discounts:active:{query_hash}"

    def _products_key(self, *, query_hash: str) -> str:
        return f"discounts:products:{query_hash}"

    async def get_active(self, *, redis_service: RedisService, query_hash: str) -> ActiveDiscountsResponse | None:
        cached = await redis_service.get(self._active_key(query_hash=query_hash))
        if cached is None:
            return None
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")
        return ActiveDiscountsResponse.model_validate_json(cached)

    async def set_active(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: ActiveDiscountsResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(self._active_key(query_hash=query_hash), response.model_dump_json(), ttl_seconds=ttl_seconds)

    async def invalidate_active(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("discounts:active:*")

    async def get_products(self, *, redis_service: RedisService, query_hash: str) -> DiscountProductsResponse | None:
        cached = await redis_service.get(self._products_key(query_hash=query_hash))
        if cached is None:
            return None
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")
        return DiscountProductsResponse.model_validate_json(cached)

    async def set_products(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: DiscountProductsResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(self._products_key(query_hash=query_hash), response.model_dump_json(), ttl_seconds=ttl_seconds)

    async def invalidate_products(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("discounts:products:*")
