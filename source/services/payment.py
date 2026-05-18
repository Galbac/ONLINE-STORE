from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
import hashlib
import hmac
import json

from source.config.settings import settings
from source.errors.auth import (
    InactiveUserError,
    PaymentAlreadyPaidError,
    PaymentAlreadyConfirmedError,
    PaymentAccessDeniedError,
    PaymentCancellationStatusNotAllowedError,
    PaymentConfirmationNotSupportedError,
    PaymentConfirmationStatusNotAllowedError,
    PaymentNotFoundError,
    PaymentProviderConfirmError,
    PaymentProviderCancelError,
    PaymentProviderCreateError,
    InvalidPaymentWebhookPayloadError,
    InvalidPaymentWebhookSignatureError,
)
from source.schemas.pydantic.payment import (
    PaymentCancelPaymentResponse,
    PaymentCancelResponse,
    PaymentConfirmResponse,
    PaymentCreateResponse,
    PaymentDetailResponse,
)


@dataclass(slots=True)
class ProviderPayment:
    provider_payment_id: str
    payment_url: str
    status: str


@dataclass(slots=True)
class ProviderPaymentStatus:
    status: str
    paid_at: object | None = None


@dataclass(slots=True)
class ProviderWebhookEvent:
    provider_event_id: str
    event_type: str
    provider_payment_id: str | None
    payment_id: int | None
    status: str | None
    payload: dict


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

    async def get_payment_status(self, *, provider_payment_id: str) -> ProviderPaymentStatus:
        return ProviderPaymentStatus(status="pending")

    async def confirm_payment(
        self,
        *,
        provider_payment_id: str,
        amount: Decimal | None = None,
    ) -> ProviderPaymentStatus:
        if settings.payments.capture_mode != "manual":
            raise PaymentConfirmationNotSupportedError
        if not provider_payment_id:
            raise PaymentProviderConfirmError
        return ProviderPaymentStatus(status="paid")

    async def cancel_payment(
        self,
        *,
        provider_payment_id: str,
        reason: str | None = None,
    ) -> ProviderPaymentStatus:
        if not provider_payment_id:
            raise PaymentProviderCancelError
        return ProviderPaymentStatus(status="cancelled")

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str | None) -> bool:
        if not settings.payments.webhook_verify_signature:
            return True
        if not signature or not settings.payments.provider_webhook_secret:
            return False
        expected_signature = hmac.new(
            settings.payments.provider_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected_signature)

    def parse_webhook_event(self, *, raw_body: bytes) -> ProviderWebhookEvent:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidPaymentWebhookPayloadError from error

        event_type = payload.get("event")
        event_object = payload.get("object")
        if not isinstance(event_type, str) or not isinstance(event_object, dict):
            raise InvalidPaymentWebhookPayloadError

        provider_payment_id = event_object.get("id")
        metadata = event_object.get("metadata") or {}
        payment_id = metadata.get("payment_id")
        try:
            parsed_payment_id = int(payment_id) if payment_id is not None else None
        except (TypeError, ValueError) as error:
            raise InvalidPaymentWebhookPayloadError from error

        provider_event_id = payload.get("id")
        if provider_event_id is None:
            if not provider_payment_id:
                raise InvalidPaymentWebhookPayloadError
            provider_event_id = f"{event_type}:{provider_payment_id}"

        return ProviderWebhookEvent(
            provider_event_id=str(provider_event_id),
            event_type=event_type,
            provider_payment_id=str(provider_payment_id) if provider_payment_id is not None else None,
            payment_id=parsed_payment_id,
            status=event_object.get("status"),
            payload=payload,
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

    async def get_payment_detail(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        payment_id: int,
        payment_repository,
        order_repository,
        payment_provider_service: PaymentProviderService,
        payment_cache_service,
        order_cache_service,
    ) -> PaymentDetailResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cached_payment = await payment_cache_service.get_detail(
            redis_service=redis_service,
            user_id=user.id,
            payment_id=payment_id,
        )
        if cached_payment is not None:
            return cached_payment

        payment = await payment_repository.get_by_id(session=session, payment_id=payment_id)
        if payment is None:
            raise PaymentNotFoundError
        order = await order_repository.get_by_id(session=session, order_id=payment.order_id)
        if order is None:
            raise PaymentNotFoundError
        if order.user_id != user.id:
            raise PaymentAccessDeniedError

        if settings.payments.status_sync_enabled and payment.provider_payment_id:
            provider_status = await payment_provider_service.get_payment_status(
                provider_payment_id=payment.provider_payment_id,
            )
            if provider_status.status != payment.status:
                try:
                    payment = await payment_repository.update_status(
                        session=session,
                        payment=payment,
                        status=provider_status.status,
                        paid_at=provider_status.paid_at,
                    )
                    await order_repository.update_payment_status(
                        session=session,
                        order=order,
                        payment_status=provider_status.status,
                    )
                    await commiter.commit()
                except Exception:
                    await commiter.rollback()
                    raise
                await order_cache_service.invalidate_order(
                    redis_service=redis_service,
                    user_id=user.id,
                    order_id=order.id,
                )

        response = self._build_detail_response(order=order, payment=payment)
        await payment_cache_service.set_detail(
            redis_service=redis_service,
            user_id=user.id,
            payment_id=payment.id,
            response=response,
            ttl_seconds=settings.payments.detail_cache_ttl_seconds,
        )
        return response

    async def confirm_payment(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        payment_id: int,
        amount: Decimal | None,
        payment_repository,
        order_repository,
        payment_provider_service: PaymentProviderService,
        payment_cache_service,
        order_cache_service,
    ) -> PaymentConfirmResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        payment = await payment_repository.get_by_id(session=session, payment_id=payment_id)
        if payment is None:
            raise PaymentNotFoundError
        order = await order_repository.get_by_id(session=session, order_id=payment.order_id)
        if order is None:
            raise PaymentNotFoundError
        if order.user_id != user.id:
            raise PaymentAccessDeniedError
        if payment.status == "paid":
            raise PaymentAlreadyConfirmedError
        if payment.status not in {"waiting_for_capture", "authorized"}:
            raise PaymentConfirmationStatusNotAllowedError
        if settings.payments.capture_mode != "manual":
            raise PaymentConfirmationNotSupportedError

        try:
            provider_status = await payment_provider_service.confirm_payment(
                provider_payment_id=payment.provider_payment_id,
                amount=amount,
            )
            normalized_status = "paid" if provider_status.status in {"paid", "succeeded"} else provider_status.status
            payment = await payment_repository.update_status(
                session=session,
                payment=payment,
                status=normalized_status,
                paid_at=provider_status.paid_at,
            )
            if normalized_status == "paid":
                await order_repository.update_payment_status(
                    session=session,
                    order=order,
                    payment_status="paid",
                )
                if order.status == "pending_payment":
                    await order_repository.update_status(
                        session=session,
                        order=order,
                        status="new",
                    )
            await commiter.commit()
        except (
            PaymentConfirmationNotSupportedError,
            PaymentProviderConfirmError,
        ):
            await commiter.rollback()
            raise
        except Exception:
            await commiter.rollback()
            raise

        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order.id,
        )
        await payment_cache_service.invalidate_detail(
            redis_service=redis_service,
            user_id=user.id,
            payment_id=payment.id,
        )
        return PaymentConfirmResponse(
            id=payment.id,
            order_id=order.id,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            paid_at=payment.paid_at,
        )

    async def cancel_payment(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        payment_id: int,
        reason: str | None,
        payment_repository,
        order_repository,
        payment_provider_service: PaymentProviderService,
        payment_cache_service,
        order_cache_service,
    ) -> PaymentCancelResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        payment = await payment_repository.get_by_id(session=session, payment_id=payment_id)
        if payment is None:
            raise PaymentNotFoundError
        order = await order_repository.get_by_id(session=session, order_id=payment.order_id)
        if order is None:
            raise PaymentNotFoundError
        if order.user_id != user.id:
            raise PaymentAccessDeniedError
        if payment.status == "paid":
            raise PaymentAlreadyPaidError
        if payment.status not in {"pending", "waiting_for_capture", "authorized"}:
            raise PaymentCancellationStatusNotAllowedError

        try:
            provider_status = await payment_provider_service.cancel_payment(
                provider_payment_id=payment.provider_payment_id,
                reason=reason,
            )
            payment = await payment_repository.update_status(
                session=session,
                payment=payment,
                status=provider_status.status,
                cancelled_at=datetime.now(settings.tz),
            )
            await order_repository.update_payment_status(
                session=session,
                order=order,
                payment_status="unpaid",
            )
            await commiter.commit()
        except PaymentProviderCancelError:
            await commiter.rollback()
            raise
        except Exception:
            await commiter.rollback()
            raise

        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order.id,
        )
        await payment_cache_service.invalidate_detail(
            redis_service=redis_service,
            user_id=user.id,
            payment_id=payment.id,
        )
        return PaymentCancelResponse(
            message="Платёж отменён",
            payment=PaymentCancelPaymentResponse(
                id=payment.id,
                order_id=order.id,
                status=payment.status,
                amount=payment.amount,
                currency=payment.currency,
                cancelled_at=payment.cancelled_at,
            ),
        )

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

    def _build_detail_response(self, *, order, payment) -> PaymentDetailResponse:
        return PaymentDetailResponse(
            id=payment.id,
            order_id=order.id,
            order_number=order.order_number,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            provider=payment.provider or settings.payments.provider,
            payment_url=payment.payment_url,
            paid_at=payment.paid_at,
            created_at=payment.created_date,
            updated_at=payment.updated_date,
        )
