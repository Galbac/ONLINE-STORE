from source.schemas.pydantic.product import (
    ProductDetailResponse,
    ProductDiscountedResponse,
    ProductListResponse,
    ProductNewResponse,
    ProductPopularResponse,
    ProductSearchResponse,
    ProductSimilarResponse,
)
from source.services.redis import RedisService


class ProductCacheService:
    def _list_key(self, query_hash: str) -> str:
        return f"products:list:{query_hash}"

    def _detail_key(self, *, product_id: int, query_hash: str) -> str:
        return f"products:detail:{product_id}:{query_hash}"

    def _slug_key(self, *, slug: str, query_hash: str) -> str:
        return f"products:slug:{slug}:{query_hash}"

    def _search_key(self, query_hash: str) -> str:
        return f"products:search:{query_hash}"

    def _popular_key(self, query_hash: str) -> str:
        return f"products:popular:{query_hash}"

    def _discounted_key(self, query_hash: str) -> str:
        return f"products:discounted:{query_hash}"

    def _new_key(self, query_hash: str) -> str:
        return f"products:new:{query_hash}"

    def _similar_key(self, *, product_id: int, query_hash: str) -> str:
        return f"products:similar:{product_id}:{query_hash}"

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

    async def get_search(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> ProductSearchResponse | None:
        cached_products = await redis_service.get(self._search_key(query_hash))
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return ProductSearchResponse.model_validate_json(cached_products)

    async def set_search(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: ProductSearchResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._search_key(query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_search(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("products:search:*")

    async def get_popular(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> ProductPopularResponse | None:
        cached_products = await redis_service.get(self._popular_key(query_hash))
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return ProductPopularResponse.model_validate_json(cached_products)

    async def set_popular(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: ProductPopularResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._popular_key(query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_popular(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("products:popular:*")

    async def get_discounted(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> ProductDiscountedResponse | None:
        cached_products = await redis_service.get(self._discounted_key(query_hash))
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return ProductDiscountedResponse.model_validate_json(cached_products)

    async def set_discounted(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: ProductDiscountedResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._discounted_key(query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_discounted(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("products:discounted:*")

    async def get_new(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
    ) -> ProductNewResponse | None:
        cached_products = await redis_service.get(self._new_key(query_hash))
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return ProductNewResponse.model_validate_json(cached_products)

    async def set_new(
        self,
        *,
        redis_service: RedisService,
        query_hash: str,
        response: ProductNewResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._new_key(query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_new(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("products:new:*")

    async def get_similar(
        self,
        *,
        redis_service: RedisService,
        product_id: int,
        query_hash: str,
    ) -> ProductSimilarResponse | None:
        cached_products = await redis_service.get(
            self._similar_key(product_id=product_id, query_hash=query_hash),
        )
        if cached_products is None:
            return None
        if isinstance(cached_products, bytes):
            cached_products = cached_products.decode("utf-8")
        return ProductSimilarResponse.model_validate_json(cached_products)

    async def set_similar(
        self,
        *,
        redis_service: RedisService,
        product_id: int,
        query_hash: str,
        response: ProductSimilarResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._similar_key(product_id=product_id, query_hash=query_hash),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_similar(self, *, redis_service: RedisService, product_id: int | None = None) -> None:
        if product_id is not None:
            await redis_service.delete_by_pattern(f"products:similar:{product_id}:*")
            return
        await redis_service.delete_by_pattern("products:similar:*")

    async def invalidate_product(self, *, redis_service: RedisService, product_id: int, slug: str | None = None) -> None:
        await redis_service.delete_by_pattern(f"products:detail:{product_id}:*")
        await redis_service.delete_by_pattern(f"products:similar:{product_id}:*")
        if slug is not None:
            await redis_service.delete_by_pattern(f"products:slug:{slug}:*")
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:search:*")
        await redis_service.delete_by_pattern("products:popular:*")
        await redis_service.delete_by_pattern("products:discounted:*")
        await redis_service.delete_by_pattern("products:new:*")

    async def invalidate_all(self, *, redis_service: RedisService) -> None:
        await redis_service.delete_by_pattern("products:list:*")
        await redis_service.delete_by_pattern("products:detail:*")
        await redis_service.delete_by_pattern("products:slug:*")
        await redis_service.delete_by_pattern("products:search:*")
        await redis_service.delete_by_pattern("products:popular:*")
        await redis_service.delete_by_pattern("products:discounted:*")
        await redis_service.delete_by_pattern("products:new:*")

    async def invalidate_by_stock_changes(self, *, redis_service: RedisService, products: list) -> None:
        for product in products:
            await self.invalidate_product(
                redis_service=redis_service,
                product_id=product.id,
                slug=getattr(product, "slug", None),
            )
        await redis_service.delete("admin:dashboard:summary")
        await redis_service.delete_by_pattern("admin:dashboard:low_stock:*")
