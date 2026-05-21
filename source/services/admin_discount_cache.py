from source.schemas.pydantic.discount import AdminDiscountDetailResponse, AdminDiscountListResponse
from source.services.redis import RedisService


class AdminDiscountCacheService:
    def _list_key(self, *, query_hash: str) -> str:
        return f"admin:discounts:list:{query_hash}"

    def _detail_key(self, *, discount_id: int) -> str:
        return f"admin:discounts:detail:{discount_id}"

    async def get_list(self, *, redis_service: RedisService, query_hash: str) -> AdminDiscountListResponse | None:
        cached_discounts = await redis_service.get(self._list_key(query_hash=query_hash))
        if cached_discounts is None:
            return None
        if isinstance(cached_discounts, bytes):
            cached_discounts = cached_discounts.decode("utf-8")
        return AdminDiscountListResponse.model_validate_json(cached_discounts)

    async def set_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminDiscountListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._list_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def get_detail(
        self,
        *,
        redis_service: RedisService,
        discount_id: int,
    ) -> AdminDiscountDetailResponse | None:
        cached_discount = await redis_service.get(self._detail_key(discount_id=discount_id))
        if cached_discount is None:
            return None
        if isinstance(cached_discount, bytes):
            cached_discount = cached_discount.decode("utf-8")
        return AdminDiscountDetailResponse.model_validate_json(cached_discount)

    async def set_detail(
        self,
        *,
        redis_service: RedisService,
        discount_id: int,
        response: AdminDiscountDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._detail_key(discount_id=discount_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:discounts:*")
