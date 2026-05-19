from source.schemas.pydantic.admin_dashboard import AdminDashboardResponse, AdminLowStockResponse, AdminSalesResponse
from source.services.redis import RedisService


class AdminDashboardCacheService:
    _summary_key = "admin:dashboard:summary"

    def _sales_key(self, *, query_hash: str) -> str:
        return f"admin:dashboard:sales:{query_hash}"

    def _low_stock_key(self, *, query_hash: str) -> str:
        return f"admin:dashboard:low_stock:{query_hash}"

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

    async def get_sales(self, *, redis_service: RedisService, query_hash: str) -> AdminSalesResponse | None:
        cached_sales = await redis_service.get(self._sales_key(query_hash=query_hash))
        if cached_sales is None:
            return None
        if isinstance(cached_sales, bytes):
            cached_sales = cached_sales.decode("utf-8")
        return AdminSalesResponse.model_validate_json(cached_sales)

    async def set_sales(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminSalesResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._sales_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_sales(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:dashboard:sales:*")

    async def get_low_stock(self, *, redis_service: RedisService, query_hash: str) -> AdminLowStockResponse | None:
        cached_low_stock = await redis_service.get(self._low_stock_key(query_hash=query_hash))
        if cached_low_stock is None:
            return None
        if isinstance(cached_low_stock, bytes):
            cached_low_stock = cached_low_stock.decode("utf-8")
        return AdminLowStockResponse.model_validate_json(cached_low_stock)

    async def set_low_stock(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminLowStockResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._low_stock_key(query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_low_stock(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:dashboard:low_stock:*")
