from source.schemas.pydantic.order import AdminOrderListResponse, OrderDetailResponse, OrderMyListResponse, OrderStatusResponse
from source.services.redis import RedisService


class OrderCacheService:
    def _admin_list_key(self, *, query_hash: str) -> str:
        return f"admin:orders:list:{query_hash}"

    def _admin_detail_key(self, *, order_id: int) -> str:
        return f"admin:orders:detail:{order_id}"

    def _my_orders_key(self, *, user_id: int, query_hash: str) -> str:
        return f"orders:my:{user_id}:{query_hash}"

    def _detail_key(self, *, user_id: int, order_id: int) -> str:
        return f"orders:detail:{user_id}:{order_id}"

    def _status_key(self, *, user_id: int, order_id: int) -> str:
        return f"orders:status:{user_id}:{order_id}"

    async def get_admin_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> AdminOrderListResponse | None:
        cached_orders = await redis_service.get(self._admin_list_key(query_hash=query_hash))
        if cached_orders is None:
            return None
        if isinstance(cached_orders, bytes):
            cached_orders = cached_orders.decode("utf-8")
        return AdminOrderListResponse.model_validate_json(cached_orders)

    async def set_admin_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminOrderListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._admin_list_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_admin_list(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:orders:list:*")

    async def get_admin_detail(
        self,
        *,
        redis_service: RedisService,
        order_id: int,
    ):
        from source.schemas.pydantic.order import AdminOrderDetailResponse

        cached_order = await redis_service.get(self._admin_detail_key(order_id=order_id))
        if cached_order is None:
            return None
        if isinstance(cached_order, bytes):
            cached_order = cached_order.decode("utf-8")
        return AdminOrderDetailResponse.model_validate_json(cached_order)

    async def set_admin_detail(
        self,
        *,
        redis_service: RedisService,
        order_id: int,
        response,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._admin_detail_key(order_id=order_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_admin_detail(
        self,
        *,
        redis_service: RedisService,
        order_id: int | None = None,
    ) -> None:
        if order_id is not None:
            await redis_service.delete(self._admin_detail_key(order_id=order_id))
            return
        await redis_service.delete_by_pattern("admin:orders:detail:*")

    async def invalidate_admin_orders(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:orders:*")

    async def get_my_orders(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        query_hash: str,
    ) -> OrderMyListResponse | None:
        cached_orders = await redis_service.get(self._my_orders_key(user_id=user_id, query_hash=query_hash))
        if cached_orders is None:
            return None
        if isinstance(cached_orders, bytes):
            cached_orders = cached_orders.decode("utf-8")
        return OrderMyListResponse.model_validate_json(cached_orders)

    async def set_my_orders(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        query_hash: str,
        response: OrderMyListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._my_orders_key(user_id=user_id, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_my_orders(self, *, redis_service: RedisService, user_id: int) -> None:
        await redis_service.delete_by_pattern(f"orders:my:{user_id}:*")

    async def get_detail(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        order_id: int,
    ) -> OrderDetailResponse | None:
        cached_order = await redis_service.get(self._detail_key(user_id=user_id, order_id=order_id))
        if cached_order is None:
            return None
        if isinstance(cached_order, bytes):
            cached_order = cached_order.decode("utf-8")
        return OrderDetailResponse.model_validate_json(cached_order)

    async def set_detail(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        order_id: int,
        response: OrderDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._detail_key(user_id=user_id, order_id=order_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_detail(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        order_id: int | None = None,
    ) -> None:
        if order_id is not None:
            await redis_service.delete(self._detail_key(user_id=user_id, order_id=order_id))
            return
        await redis_service.delete_by_pattern(f"orders:detail:{user_id}:*")

    async def invalidate_order(self, *, redis_service: RedisService, user_id: int, order_id: int) -> None:
        await self.invalidate_detail(redis_service=redis_service, user_id=user_id, order_id=order_id)
        await self.invalidate_status(redis_service=redis_service, user_id=user_id, order_id=order_id)
        await self.invalidate_my_orders(redis_service=redis_service, user_id=user_id)
        await self.invalidate_admin_list(redis_service=redis_service)
        await self.invalidate_admin_detail(redis_service=redis_service, order_id=order_id)

    async def get_status(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        order_id: int,
    ) -> OrderStatusResponse | None:
        cached_status = await redis_service.get(self._status_key(user_id=user_id, order_id=order_id))
        if cached_status is None:
            return None
        if isinstance(cached_status, bytes):
            cached_status = cached_status.decode("utf-8")
        return OrderStatusResponse.model_validate_json(cached_status)

    async def set_status(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        order_id: int,
        response: OrderStatusResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._status_key(user_id=user_id, order_id=order_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_status(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        order_id: int | None = None,
    ) -> None:
        if order_id is not None:
            await redis_service.delete(self._status_key(user_id=user_id, order_id=order_id))
            return
        await redis_service.delete_by_pattern(f"orders:status:{user_id}:*")
