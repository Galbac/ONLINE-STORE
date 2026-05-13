from source.services.redis import RedisService


class CartCacheService:
    async def invalidate_cart(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete(f"cart:{user_id}")
        await redis_service.delete(f"cart:summary:{user_id}")
