from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.payment_webhook_log import PaymentWebhookLog


class PaymentWebhookLogRepository:
    async def exists_by_event_id(self, *, session: AsyncSession, provider_event_id: str) -> bool:
        result = await session.execute(
            select(PaymentWebhookLog.id)
            .where(PaymentWebhookLog.provider_event_id == provider_event_id)
            .limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        session: AsyncSession,
        provider_event_id: str,
        event_type: str | None,
        provider_payment_id: str | None,
        payment_id: int | None,
        payload: dict,
        processing_status: str,
        error_message: str | None = None,
    ) -> PaymentWebhookLog:
        webhook_log = PaymentWebhookLog(
            provider_event_id=provider_event_id,
            event_type=event_type,
            provider_payment_id=provider_payment_id,
            payment_id=payment_id,
            payload=payload,
            processing_status=processing_status,
            error_message=error_message,
        )
        session.add(webhook_log)
        await session.flush()
        await session.refresh(webhook_log)
        return webhook_log
