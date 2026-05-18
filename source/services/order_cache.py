from source.schemas.pydantic.order import OrderMyListResponse
from source.services.redis import RedisService


class OrderCacheService:
    def _my_orders_key(self, *, user_id: int, query_hash: str) -> str:
        return f"orders:my:{user_id}:{query_hash}"

    async def get_my_orders(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        query_hash: str,
    ) -> OrderMyListResponse | None:
        cached_orders = await redis_service.get(self._my_orders_key(user_id=user_id, query_hash=query_hash))
        if cached_orders is None:
            return None
        if isinstance(cached_orders, bytes):
            cached_orders = cached_orders.decode("utf-8")
        return OrderMyListResponse.model_validate_json(cached_orders)

    async def set_my_orders(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        query_hash: str,
        response: OrderMyListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._my_orders_key(user_id=user_id, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_my_orders(self, *, redis_service: RedisService, user_id: int) -> None:
        await redis_service.delete_by_pattern(f"orders:my:{user_id}:*")
