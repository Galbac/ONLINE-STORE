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
    ) -> PaymentWebhookResponse:
        if not payment_provider_service.verify_webhook_signature(raw_body=raw_body, signature=signature):
            from source.errors.auth import InvalidPaymentWebhookSignatureError

            raise InvalidPaymentWebhookSignatureError

        event = payment_provider_service.parse_webhook_event(raw_body=raw_body)
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
            payment = await payment_repository.get_by_id(session=session, payment_id=event.payment_id)

        if payment is None:
            await payment_webhook_log_repository.create(
                session=session,
                provider_event_id=event.provider_event_id,
                event_type=event.event_type,
                provider_payment_id=event.provider_payment_id,
                payment_id=event.payment_id,
                payload=event.payload,
                processing_status="payment_not_found",
                error_message="Payment not found",
            )
            await commiter.commit()
            return PaymentWebhookResponse(message="Webhook processed")

        order = await order_repository.get_by_id(session=session, order_id=payment.order_id)
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

        try:
            await payment_webhook_log_repository.create(
                session=session,
                provider_event_id=event.provider_event_id,
                event_type=event.event_type,
                provider_payment_id=event.provider_payment_id,
                payment_id=payment.id,
                payload=event.payload,
                processing_status="processed",
            )
            payment_succeeded = event.event_type == "payment.succeeded"
            if payment_succeeded:
                await payment_repository.update_status(
                    session=session,
                    payment=payment,
                    status="paid",
                    paid_at=payment.paid_at,
                )
                await order_repository.update_payment_status(session=session, order=order, payment_status="paid")
                if order.status == "pending_payment":
                    await order_repository.update_status(session=session, order=order, status="new")
                await one_c_integration_service.mark_order_pending_sync(order=order)
            elif event.event_type == "payment.canceled":
                await payment_repository.update_status(session=session, payment=payment, status="cancelled")
                await order_repository.update_payment_status(session=session, order=order, payment_status="cancelled")
            elif event.event_type == "payment.failed":
                await payment_repository.update_status(session=session, payment=payment, status="failed")
                await order_repository.update_payment_status(session=session, order=order, payment_status="failed")
            elif event.event_type == "refund.succeeded":
                payment.refund_status = "refunded"
                await payment_repository.update_status(
                    session=session,
                    payment=payment,
                    status=payment.status,
                    paid_at=payment.paid_at,
                )
                await order_repository.update_payment_status(session=session, order=order, payment_status="refunded")
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
        await profile_cache_service.delete_summary(redis_service=redis_service, user_id=order.user_id)
        if event.event_type == "payment.succeeded":
            await notification_service.notify_payment_success(
                email_service=email_service,
                telegram_service=telegram_service,
                order=order,
            )
        return PaymentWebhookResponse(message="Webhook processed")
