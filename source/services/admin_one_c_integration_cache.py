from source.schemas.pydantic.one_c import AdminOneCLogsResponse
from source.services.redis import RedisService


class AdminOneCIntegrationCacheService:
    def _logs_key(self, *, query_hash: str) -> str:
        return f"admin:integration:1c:logs:{query_hash}"

    async def get_logs(self, *, redis_service: RedisService, query_hash: str) -> AdminOneCLogsResponse | None:
        cached_logs = await redis_service.get(self._logs_key(query_hash=query_hash))
        if cached_logs is None:
            return None
        if isinstance(cached_logs, bytes):
            cached_logs = cached_logs.decode("utf-8")
        return AdminOneCLogsResponse.model_validate_json(cached_logs)

    async def set_logs(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminOneCLogsResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._logs_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )
