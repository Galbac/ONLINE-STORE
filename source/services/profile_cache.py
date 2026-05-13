from source.schemas.pydantic.profile import ProfileSummaryResponse
from source.services.redis import RedisService


class ProfileCacheService:
    def _summary_key(self, user_id: int) -> str:
        return f"profile:summary:{user_id}"

    async def get_summary(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> ProfileSummaryResponse | None:
        cached_summary = await redis_service.get(self._summary_key(user_id))
        if cached_summary is None:
            return None
        if isinstance(cached_summary, bytes):
            cached_summary = cached_summary.decode("utf-8")
        return ProfileSummaryResponse.model_validate_json(cached_summary)

    async def set_summary(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        response: ProfileSummaryResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._summary_key(user_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def delete_summary(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete(self._summary_key(user_id))
