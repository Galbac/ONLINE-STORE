from source.schemas.pydantic.admin_dashboard import AdminDashboardResponse
from source.services.redis import RedisService


class AdminDashboardCacheService:
    _summary_key = "admin:dashboard:summary"

    async def get_summary(self, *, redis_service: RedisService) -> AdminDashboardResponse | None:
        cached_summary = await redis_service.get(self._summary_key)
        if cached_summary is None:
            return None
        if isinstance(cached_summary, bytes):
            cached_summary = cached_summary.decode("utf-8")
        return AdminDashboardResponse.model_validate_json(cached_summary)

    async def set_summary(
        self,
        *,
        redis_service: RedisService,
        response: AdminDashboardResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._summary_key,
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_summary(self, *, redis_service: RedisService) -> None:
        await redis_service.delete(self._summary_key)
