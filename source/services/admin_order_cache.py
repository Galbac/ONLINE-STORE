from source.services.order_cache import OrderCacheService
from source.services.redis import RedisService


class AdminOrderCacheService:
    async def invalidate_order(self, *, redis_service: RedisService, order_id: int) -> None:
        order_cache_service = OrderCacheService()
        await order_cache_service.invalidate_admin_detail(redis_service=redis_service, order_id=order_id)
        await order_cache_service.invalidate_admin_list(redis_service=redis_service)
