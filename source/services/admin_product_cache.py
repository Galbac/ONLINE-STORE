from source.schemas.pydantic.admin_product import AdminProductDetailResponse, AdminProductListResponse
from source.services.redis import RedisService


class AdminProductCacheService:
    def _list_key(self, *, query_hash: str) -> str:
        return f"admin:products:list:{query_hash}"

    def _detail_key(self, *, product_id: int) -> str:
        return f"admin:products:detail:{product_id}"

    async def get_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> AdminProductListResponse | None:
        cached_products = await redis_service.get(self._list_key(query_hash=query_hash))
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return AdminProductListResponse.model_validate_json(cached_products)

    async def set_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: AdminProductListResponse,
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
        product_id: int,
    ) -> AdminProductDetailResponse | None:
        cached_product = await redis_service.get(self._detail_key(product_id=product_id))
        if cached_product is None:
            return None
        if isinstance(cached_product, bytes):
            cached_product = cached_product.decode("utf-8")
        return AdminProductDetailResponse.model_validate_json(cached_product)

    async def set_detail(
        self,
        *,
        redis_service: RedisService,
        product_id: int,
        response: AdminProductDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._detail_key(product_id=product_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_list(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:products:list:*")

    async def invalidate_product(self, *, redis_service: RedisService, product_id: int) -> None:
        await redis_service.delete(self._detail_key(product_id=product_id))
        await redis_service.delete_by_pattern("admin:products:list:*")

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("admin:products:list:*")
        await redis_service.delete_by_pattern("admin:products:detail:*")
