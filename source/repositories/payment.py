from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from source.db.models.payment import Payment


class PaymentRepository:
    async def create(
        self,
        *,
        session: AsyncSession,
        order_id: int,
        amount: Decimal,
        currency: str = "RUB",
        status: str,
        provider: str | None = None,
        payment_url: str | None,
    ) -> Payment:
        payment = Payment(
            order_id=order_id,
            amount=amount,
            currency=currency,
            status=status,
            provider=provider,
            payment_url=payment_url,
        )
        session.add(payment)
        await session.flush()
        await session.refresh(payment)
        return payment

    async def get_by_order_id(self, *, session: AsyncSession, order_id: int) -> Payment | None:
        result = await session.execute(select(Payment).where(Payment.order_id == order_id))
        return result.scalar_one_or_none()

    async def get_by_order_ids(self, *, session: AsyncSession, order_ids: list[int]) -> list[Payment]:
        if not order_ids:
            return []
        result = await session.execute(select(Payment).where(Payment.order_id.in_(order_ids)))
        return list(result.scalars().all())

    async def get_by_id(self, *, session: AsyncSession, payment_id: int) -> Payment | None:
        result = await session.execute(select(Payment).where(Payment.id == payment_id))
        return result.scalar_one_or_none()

    async def get_by_provider_payment_id(
        self,
        *,
        session: AsyncSession,
        provider_payment_id: str,
    ) -> Payment | None:
        result = await session.execute(
            select(Payment).where(Payment.provider_payment_id == provider_payment_id),
        )
        return result.scalar_one_or_none()

    async def get_active_by_order_id(self, *, session: AsyncSession, order_id: int) -> Payment | None:
        result = await session.execute(
            select(Payment)
            .where(
                Payment.order_id == order_id,
                Payment.status.in_(("unpaid", "pending", "waiting_for_capture")),
            )
            .order_by(Payment.created_date.desc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def update_provider_data(
        self,
        *,
        session: AsyncSession,
        payment: Payment,
        provider_payment_id: str,
        payment_url: str,
        status: str,
    ) -> Payment:
        payment.provider_payment_id = provider_payment_id
        payment.payment_url = payment_url
        payment.status = status
        session.add(payment)
        await session.flush()
        await session.refresh(payment)
        return payment

    async def update_status(
        self,
        *,
        session: AsyncSession,
        payment: Payment,
        status: str,
        paid_at=None,
        cancelled_at=None,
    ) -> Payment:
        payment.status = status
        payment.paid_at = paid_at
        payment.cancelled_at = cancelled_at
        session.add(payment)
        await session.flush()
        await session.refresh(payment)
        return payment

    async def update_refund_status(
        self,
        *,
        session: AsyncSession,
        payment: Payment,
        refund_status: str,
    ) -> Payment:
        payment.refund_status = refund_status
        session.add(payment)
        await session.flush()
        await session.refresh(payment)
        return payment
