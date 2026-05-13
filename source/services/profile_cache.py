from source.schemas.pydantic.profile import AddressListResponse, ProfileOrderListResponse, ProfileSummaryResponse
from source.services.redis import RedisService


class ProfileCacheService:
    def _summary_key(self, user_id: int) -> str:
        return f"profile:summary:{user_id}"

    def _addresses_key(self, *, user_id: int, include_deleted: bool, limit: int, offset: int) -> str:
        include_deleted_value = str(include_deleted).lower()
        return f"profile:addresses:{user_id}:include_deleted:{include_deleted_value}:limit:{limit}:offset:{offset}"

    def _orders_key(self, *, user_id: int, query_hash: str) -> str:
        return f"profile:orders:{user_id}:{query_hash}"

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

    async def get_addresses(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        include_deleted: bool,
        limit: int,
        offset: int,
    ) -> AddressListResponse | None:
        cached_addresses = await redis_service.get(
            self._addresses_key(
                user_id=user_id,
                include_deleted=include_deleted,
                limit=limit,
                offset=offset,
            ),
        )
        if cached_addresses is None:
            return None
        if isinstance(cached_addresses, bytes):
            cached_addresses = cached_addresses.decode("utf-8")
        return AddressListResponse.model_validate_json(cached_addresses)

    async def set_addresses(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        include_deleted: bool,
        limit: int,
        offset: int,
        response: AddressListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._addresses_key(
                user_id=user_id,
                include_deleted=include_deleted,
                limit=limit,
                offset=offset,
            ),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_addresses(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete_by_pattern(f"profile:addresses:{user_id}:*")

    async def get_orders(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        query_hash: str,
    ) -> ProfileOrderListResponse | None:
        cached_orders = await redis_service.get(self._orders_key(user_id=user_id, query_hash=query_hash))
        if cached_orders is None:
            return None
        if isinstance(cached_orders, bytes):
            cached_orders = cached_orders.decode("utf-8")
        return ProfileOrderListResponse.model_validate_json(cached_orders)

    async def set_orders(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        query_hash: str,
        response: ProfileOrderListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._orders_key(user_id=user_id, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_orders(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        await redis_service.delete_by_pattern(f"profile:orders:{user_id}:*")
