from source.schemas.pydantic.user import UserMeResponse
from source.services.redis import RedisService


class UserCacheService:
    def _user_me_key(self, user_id: int) -> str:
        return f"users:me:{user_id}"

    async def get_user_me_cache(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> UserMeResponse | None:
        cached_user = await redis_service.get(self._user_me_key(user_id))
        if cached_user is None:
            return None
        if isinstance(cached_user, bytes):
            cached_user = cached_user.decode("utf-8")
        return UserMeResponse.model_validate_json(cached_user)

    async def set_user_me_cache(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        response: UserMeResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._user_me_key(user_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def delete_user_me_cache(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete(self._user_me_key(user_id))
