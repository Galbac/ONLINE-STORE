from source.schemas.pydantic.payment import PaymentDetailResponse
from source.services.redis import RedisService


class PaymentCacheService:
    def _detail_key(self, *, user_id: int, payment_id: int) -> str:
        return f"payments:detail:{user_id}:{payment_id}"

    async def get_detail(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        payment_id: int,
    ) -> PaymentDetailResponse | None:
        cached_payment = await redis_service.get(self._detail_key(user_id=user_id, payment_id=payment_id))
        if cached_payment is None:
            return None
        if isinstance(cached_payment, bytes):
            cached_payment = cached_payment.decode("utf-8")
        return PaymentDetailResponse.model_validate_json(cached_payment)

    async def set_detail(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        payment_id: int,
        response: PaymentDetailResponse,
        ttl_seconds: int,
    ) -> None:
        await redis_service.set(
            self._detail_key(user_id=user_id, payment_id=payment_id),
            response.model_dump_json(),
            ttl_seconds=ttl_seconds,
        )

    async def invalidate_detail(self, *, redis_service: RedisService, user_id: int, payment_id: int) -> None:
        await redis_service.delete(self._detail_key(user_id=user_id, payment_id=payment_id))

    async def invalidate_payment(self, *, redis_service: RedisService, user_id: int, payment_id: int) -> None:
        await self.invalidate_detail(redis_service=redis_service, user_id=user_id, payment_id=payment_id)
