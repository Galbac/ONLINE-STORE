from source.services.redis import RedisService
from source.schemas.pydantic.cart import CartResponse, CartSummaryResponse


class CartCacheService:
    def _cart_key(self, user_id: int) -> str:
        return f"cart:{user_id}"

    def _summary_key(self, user_id: int) -> str:
        return f"cart:summary:{user_id}"

    async def get_cart(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> CartResponse | None:
        cached_cart = await redis_service.get(self._cart_key(user_id))
        if cached_cart is None:
            return None
        if isinstance(cached_cart, bytes):
            cached_cart = cached_cart.decode("utf-8")
        return CartResponse.model_validate_json(cached_cart)

    async def set_cart(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        response: CartResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._cart_key(user_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_cart(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete(self._cart_key(user_id))
        await self.invalidate_summary(redis_service=redis_service, user_id=user_id)

    async def get_summary(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> CartSummaryResponse | None:
        cached_summary = await redis_service.get(self._summary_key(user_id))
        if cached_summary is None:
            return None
        if isinstance(cached_summary, bytes):
            cached_summary = cached_summary.decode("utf-8")
        return CartSummaryResponse.model_validate_json(cached_summary)

    async def set_summary(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        response: CartSummaryResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._summary_key(user_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_summary(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete(self._summary_key(user_id))

    async def invalidate_all_summaries(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("cart:summary:*")
