from source.schemas.pydantic.admin_staff import AdminStaffListResponse
from source.services.redis import RedisService


class AdminStaffCacheService:
    def _list_key(self, *, query_hash: str) -> str:
        return f"admin:staff:list:{query_hash}"

    async def get_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> AdminStaffListResponse | None:
        cached_staff = await redis_service.get(self._list_key(query_hash=query_hash))
        if cached_staff is None:
            return None
        if isinstance(cached_staff, bytes):
            cached_staff = cached_staff.decode("utf-8")
        return AdminStaffListResponse.model_validate_json(cached_staff)

    async def set_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminStaffListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._list_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:staff:*")
