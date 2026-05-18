from dataclasses import dataclass
from decimal import Decimal

from source.config.settings import settings
from source.errors.auth import PaymentProviderCreateError
from source.schemas.pydantic.payment import PaymentCreateResponse


@dataclass(slots=True)
class ProviderPayment:
    provider_payment_id: str
    payment_url: str
    status: str


class PaymentProviderService:
    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        order_number: str,
        description: str,
        return_url: str,
        webhook_url: str,
        customer_email: str | None = None,
    ) -> ProviderPayment:
        provider = settings.payments.provider
        if provider != "yookassa":
            raise PaymentProviderCreateError
        if not settings.payments.provider_shop_id or not settings.payments.provider_secret_key:
            raise PaymentProviderCreateError

        return ProviderPayment(
            provider_payment_id=f"{provider}-{order_number}",
            payment_url=f"https://payment.example.com/pay/{order_number}",
            status="pending",
        )


class PaymentService:
    async def create_payment(
        self,
        *,
        payment_repository,
        session,
        order,
        commiter=None,
        redis_service=None,
        user=None,
        order_repository=None,
        order_service=None,
        payment_provider_service: PaymentProviderService | None = None,
        order_cache_service=None,
    ):
        # Старый сценарий используется при создании заказа.
        if commiter is None:
            payment_url = f"https://payment.example.com/pay/{order.id}"
            await payment_repository.create(
                session=session,
                order_id=order.id,
                amount=order.final_price,
                currency=settings.payments.currency,
                status="unpaid",
                provider=settings.payments.provider,
                payment_url=payment_url,
            )
            return payment_url

        active_payment = None
        try:
            order_service.validate_order_for_payment(order=order, user=user)
            active_payment = await payment_repository.get_active_by_order_id(session=session, order_id=order.id)
            if active_payment is not None:
                return self._build_response(order=order, payment=active_payment)

            payment = await payment_repository.create(
                session=session,
                order_id=order.id,
                amount=order.final_price,
                currency=settings.payments.currency,
                status="pending",
                provider=settings.payments.provider,
                payment_url=None,
            )
            provider_payment = await payment_provider_service.create_payment(
                amount=order.final_price,
                currency=settings.payments.currency,
                order_number=order.order_number,
                description=f"Оплата заказа {order.order_number}",
                return_url=settings.payments.return_url,
                webhook_url=settings.payments.webhook_url,
                customer_email=order.customer_email,
            )
            payment = await payment_repository.update_provider_data(
                session=session,
                payment=payment,
                provider_payment_id=provider_payment.provider_payment_id,
                payment_url=provider_payment.payment_url,
                status=provider_payment.status,
            )
            if order.payment_status != "pending":
                await order_repository.update_payment_status(
                    session=session,
                    order=order,
                    payment_status="pending",
                )
            await commiter.commit()
        except Exception as error:
            await commiter.rollback()
            if isinstance(error, PaymentProviderCreateError):
                raise
            raise

        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order.id,
        )
        return self._build_response(order=order, payment=payment)

    async def create_refund_request(self, *, order) -> None:
        return None

    def _build_response(self, *, order, payment) -> PaymentCreateResponse:
        return PaymentCreateResponse(
            id=payment.id,
            order_id=order.id,
            order_number=order.order_number,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            provider=payment.provider or settings.payments.provider,
            payment_url=payment.payment_url,
            created_at=payment.created_date,
        )
