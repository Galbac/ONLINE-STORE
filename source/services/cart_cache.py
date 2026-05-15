from source.services.redis import RedisService
from source.schemas.pydantic.cart import CartResponse


class CartCacheService:
    def _cart_key(self, user_id: int) -> str:
        return f"cart:{user_id}"

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
        await redis_service.delete(f"cart:summary:{user_id}")
