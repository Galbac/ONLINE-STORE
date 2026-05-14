from source.schemas.pydantic.product import ProductDetailResponse, ProductListResponse
from source.services.redis import RedisService


class ProductCacheService:
    def _list_key(self, query_hash: str) -> str:
        return f"products:list:{query_hash}"

    def _detail_key(self, *, product_id: int, query_hash: str) -> str:
        return f"products:detail:{product_id}:{query_hash}"

    def _slug_key(self, *, slug: str, query_hash: str) -> str:
        return f"products:slug:{slug}:{query_hash}"

    async def get_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> ProductListResponse | None:
        cached_products = await redis_service.get(self._list_key(query_hash))
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return ProductListResponse.model_validate_json(cached_products)

    async def set_list(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: ProductListResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._list_key(query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def get_detail(
        self,
        *,
        redis_service: RedisService,
        product_id: int,
        query_hash: str,
    ) -> ProductDetailResponse | None:
        cached_product = await redis_service.get(
            self._detail_key(product_id=product_id, query_hash=query_hash),
        )
        if cached_product is None:
            return None
        if isinstance(cached_product, bytes):
            cached_product = cached_product.decode("utf-8")
        return ProductDetailResponse.model_validate_json(cached_product)

    async def set_detail(
        self,
        *,
        redis_service: RedisService,
        product_id: int,
        query_hash: str,
        response: ProductDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._detail_key(product_id=product_id, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def get_by_slug(
        self,
        *,
        redis_service: RedisService,
        slug: str,
        query_hash: str,
    ) -> ProductDetailResponse | None:
        cached_product = await redis_service.get(
            self._slug_key(slug=slug, query_hash=query_hash),
        )
        if cached_product is None:
            return None
        if isinstance(cached_product, bytes):
            cached_product = cached_product.decode("utf-8")
        return ProductDetailResponse.model_validate_json(cached_product)

    async def set_by_slug(
        self,
        *,
        redis_service: RedisService,
        slug: str,
        query_hash: str,
        response: ProductDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._slug_key(slug=slug, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_product(self, *, redis_service: RedisService, product_id: int, slug: str | None = None) -> None:
        await redis_service.delete_by_pattern(f"products:detail:{product_id}:*")
        await redis_service.delete_by_pattern(f"products:similar:{product_id}:*")
        if slug is not None:
            await redis_service.delete_by_pattern(f"products:slug:{slug}:*")
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:search:*")

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:detail:*")
        await redis_service.delete_by_pattern("products:slug:*")
        await redis_service.delete_by_pattern("products:search:*")
        await redis_service.delete_by_pattern("products:popular:*")
        await redis_service.delete_by_pattern("products:discounted:*")
        await redis_service.delete_by_pattern("products:new:*")
