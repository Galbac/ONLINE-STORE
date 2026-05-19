from source.schemas.pydantic.admin_auth import AdminMeResponse
from source.services.redis import RedisService


class AdminAuthCacheService:
    def _me_key(self, *, user_id: int) -> str:
        return f"admin:auth:me:{user_id}"

    async def get_me(self, *, redis_service: RedisService, user_id: int) -> AdminMeResponse | None:
        cached_user = await redis_service.get(self._me_key(user_id=user_id))
        if cached_user is None:
            return None
        if isinstance(cached_user, bytes):
            cached_user = cached_user.decode("utf-8")
        return AdminMeResponse.model_validate_json(cached_user)

    async def set_me(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        response: AdminMeResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._me_key(user_id=user_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_me(self, *, redis_service: RedisService, user_id: int) -> None:
        await redis_service.delete(self._me_key(user_id=user_id))
