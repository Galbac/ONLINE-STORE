from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import urllib.parse
from sqlalchemy import select, func
from source.db.models.refund import Refund
from sqlalchemy import text
from source.errors.auth import InvalidPaymentWebhookPayloadError
from source.config.settings import settings
from source.schemas.pydantic.payment import PaymentWebhookResponse


class PaymentWebhookService:
    async def process_webhook(
        self,
        *,
        raw_body: bytes,
        signature: str | None,
        session,
        commiter,
        redis_service,
        payment_provider_service,
        payment_repository,
        payment_webhook_log_repository,
        order_repository,
        payment_cache_service,
        order_cache_service,
        profile_cache_service,
        notification_service,
        email_service,
        telegram_service,
        one_c_integration_service,
        settings_repository=None,
        notification_repository=None,
        web_push_service=None,
        push_subscription_repository=None,
        product_cache_service=None,
    ) -> PaymentWebhookResponse:
        robokassa_pwd_2 = getattr(settings.payments, "robokassa_password_2", None)
        if settings_repository is not None and session is not None:
            store_settings, _ = await settings_repository.get_or_create_default(
                session=session
            )
            if store_settings is not None and getattr(
                store_settings, "robokassa_password_2", None
            ):
                robokassa_pwd_2 = store_settings.robokassa_password_2

        event = payment_provider_service.parse_webhook_event(raw_body=raw_body)
        if "OutSum" in event.payload:
            if not payment_provider_service.verify_webhook_signature(
                raw_body=raw_body,
                signature=signature,
                robokassa_password_2=robokassa_pwd_2,
            ):
                from source.errors.auth import InvalidPaymentWebhookSignatureError

                raise InvalidPaymentWebhookSignatureError
        else:
            object_id = event.payload["object"].get("id")
            if not isinstance(object_id, str) or not object_id:
                raise InvalidPaymentWebhookPayloadError
            kind = "refunds" if event.event_type.startswith("refund.") else "payments"
            verified = await payment_provider_service.request_yookassa(
                method="GET",
                path=kind + "/" + urllib.parse.quote(object_id, safe=""),
                session=session,
            )
            if verified.get("id") != object_id:
                raise InvalidPaymentWebhookPayloadError
            expected = {
                "payment.succeeded": "succeeded",
                "payment.canceled": "canceled",
                "refund.succeeded": "succeeded",
            }
            if (
                event.event_type not in expected
                or verified.get("status") != expected[event.event_type]
            ):
                return PaymentWebhookResponse(message="Webhook ignored")
            event = payment_provider_service.parse_webhook_event(
                raw_body=json.dumps(
                    {"event": event.event_type, "object": verified}
                ).encode(),
            )
        event_lock = int.from_bytes(
            hashlib.sha256(event.provider_event_id.encode()).digest()[:8],
            "big",
            signed=True,
        )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": event_lock}
        )
        if await payment_webhook_log_repository.exists_by_event_id(
            session=session,
            provider_event_id=event.provider_event_id,
        ):
            return PaymentWebhookResponse(message="Webhook processed")

        payment = None
        if event.provider_payment_id is not None:
            payment = await payment_repository.get_by_provider_payment_id(
                session=session,
                provider_payment_id=event.provider_payment_id,
            )
        if payment is None and event.payment_id is not None:
            payment = await payment_repository.get_by_id(
                session=session, payment_id=event.payment_id
            )

        if payment is None:
            # The provider may notify before the payment transaction commits.
            raise RuntimeError("Payment not committed yet; retry webhook")

        await session.refresh(payment, with_for_update=True)
        if event.event_type == "payment.succeeded":
            amount_data = event.payload.get("object", {}).get("amount", {})
            if not isinstance(amount_data, dict):
                raise InvalidPaymentWebhookPayloadError
            raw_amount = event.payload.get("OutSum", amount_data.get("value"))
            currency = amount_data.get(
                "currency", "RUB" if "OutSum" in event.payload else None
            )
            try:
                amount = Decimal(str(raw_amount))
            except (InvalidOperation, TypeError, ValueError) as error:
                raise InvalidPaymentWebhookPayloadError from error
            if (
                not amount.is_finite()
                or amount != payment.amount
                or currency != payment.currency
            ):
                raise InvalidPaymentWebhookPayloadError
            if (
                event.provider_payment_id
                and payment.provider_payment_id != event.provider_payment_id
            ):
                raise InvalidPaymentWebhookPayloadError

        order = await order_repository.get_by_id(
            session=session, order_id=payment.order_id
        )
        if order is None:
            await payment_webhook_log_repository.create(
                session=session,
                provider_event_id=event.provider_event_id,
                event_type=event.event_type,
                provider_payment_id=event.provider_payment_id,
                payment_id=payment.id,
                payload=event.payload,
                processing_status="order_not_found",
                error_message="Order not found",
            )
            await commiter.commit()
            return PaymentWebhookResponse(message="Webhook processed")

        ignore_event = (
            (
                event.event_type in {"payment.failed", "payment.canceled"}
                and payment.status == "paid"
            )
            or (event.event_type == "payment.succeeded" and payment.status == "paid")
            or (
                event.event_type == "refund.succeeded"
                and payment.refund_status == "refunded"
            )
        )
        try:
            await payment_webhook_log_repository.create(
                session=session,
                provider_event_id=event.provider_event_id,
                event_type=event.event_type,
                provider_payment_id=event.provider_payment_id,
                payment_id=payment.id,
                payload=event.payload,
                processing_status="ignored" if ignore_event else "processed",
            )
            if ignore_event:
                await commiter.commit()
                return PaymentWebhookResponse(message="Webhook processed")
            payment_succeeded = event.event_type == "payment.succeeded"
            if payment_succeeded:
                await payment_repository.update_status(
                    session=session,
                    payment=payment,
                    status="paid",
                    paid_at=payment.paid_at or datetime.now(settings.tz),
                )
                await order_repository.update_payment_status(
                    session=session, order=order, payment_status="paid"
                )
                if order.status == "pending_payment":
                    await order_repository.update_status(
                        session=session, order=order, status="new"
                    )
                await one_c_integration_service.mark_order_pending_sync(order=order)
            elif event.event_type == "payment.canceled":
                await payment_repository.update_status(
                    session=session, payment=payment, status="cancelled"
                )
                await order_repository.update_payment_status(
                    session=session, order=order, payment_status="cancelled"
                )
            elif event.event_type == "payment.failed":
                await payment_repository.update_status(
                    session=session, payment=payment, status="failed"
                )
                await order_repository.update_payment_status(
                    session=session, order=order, payment_status="failed"
                )
            elif event.event_type == "refund.succeeded":
                refund_data = event.payload["object"]
                amount_data = refund_data.get("amount", {})
                try:
                    amount = Decimal(str(amount_data.get("value")))
                except (AttributeError, InvalidOperation, ValueError) as error:
                    raise InvalidPaymentWebhookPayloadError from error
                if (
                    not amount.is_finite()
                    or amount <= 0
                    or amount > payment.amount
                    or amount_data.get("currency") != payment.currency
                ):
                    raise InvalidPaymentWebhookPayloadError
                refund = await session.scalar(
                    select(Refund).where(Refund.provider_refund_id == refund_data["id"])
                )
                if refund is None:
                    refund = Refund(
                        payment_id=payment.id,
                        amount=amount,
                        currency=payment.currency,
                        status="succeeded",
                        provider_refund_id=refund_data["id"],
                    )
                    session.add(refund)
                elif refund.payment_id != payment.id or refund.amount != amount:
                    raise InvalidPaymentWebhookPayloadError
                else:
                    refund.status = "succeeded"
                await session.flush()
                total = await session.scalar(
                    select(func.coalesce(func.sum(Refund.amount), 0)).where(
                        Refund.payment_id == payment.id, Refund.status == "succeeded"
                    )
                )
                payment.refund_status = (
                    "refunded" if total >= payment.amount else "partial_refunded"
                )
                await order_repository.update_payment_status(
                    session=session, order=order, payment_status=payment.refund_status
                )
            await commiter.commit()
        except Exception:
            await commiter.rollback()
            raise

        await payment_cache_service.invalidate_payment(
            redis_service=redis_service,
            user_id=order.user_id,
            payment_id=payment.id,
        )
        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=order.user_id,
            order_id=order.id,
        )
        await profile_cache_service.delete_summary(
            redis_service=redis_service, user_id=order.user_id
        )
        if event.event_type == "payment.succeeded" and product_cache_service is not None:
            await product_cache_service.invalidate_popular(redis_service=redis_service)
        if event.event_type == "payment.succeeded":
            await notification_service.notify_payment_success(
                email_service=email_service,
                telegram_service=telegram_service,
                order=order,
                session=session,
                notification_repository=notification_repository,
                web_push_service=web_push_service,
                push_subscription_repository=push_subscription_repository,
            )
            await commiter.commit()
        elif (
            event.event_type in {"payment.failed", "payment.canceled"}
            and notification_repository is not None
        ):
            await notification_repository.create(
                session=session,
                user_id=order.user_id,
                type="payment",
                title=f"Не удалось оплатить заказ {order.order_number}",
                message="Платёж не прошёл или был отменён. Откройте заказ, чтобы проверить статус и выбрать способ оплаты.",
            )
            await commiter.commit()
            if (
                web_push_service is not None
                and push_subscription_repository is not None
            ):
                await web_push_service.send_to_user(
                    session=session,
                    push_subscription_repository=push_subscription_repository,
                    user_id=order.user_id,
                    title=f"Не удалось оплатить заказ {order.order_number}",
                    body="Платёж не прошёл или был отменён. Откройте заказ, чтобы проверить статус.",
                    url=f"/profile/orders/{order.id}",
                )
        elif (
            event.event_type == "refund.succeeded"
            and notification_repository is not None
        ):
            await notification_repository.create(
                session=session,
                user_id=order.user_id,
                type="payment",
                title=f"Возврат по заказу {order.order_number} выполнен",
                message="Платёжная система подтвердила возврат средств.",
            )
            await commiter.commit()
            if (
                web_push_service is not None
                and push_subscription_repository is not None
            ):
                await web_push_service.send_to_user(
                    session=session,
                    push_subscription_repository=push_subscription_repository,
                    user_id=order.user_id,
                    title=f"Возврат по заказу {order.order_number} выполнен",
                    body="Платёжная система подтвердила возврат средств.",
                    url=f"/profile/orders/{order.id}",
                )
        return PaymentWebhookResponse(message="Webhook processed")
