from source.services.redis import RedisService


class AuthCacheService:
    async def delete_current_user_cache(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete(f"auth:me:user:{user_id}")
