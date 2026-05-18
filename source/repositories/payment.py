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
        status: str,
        payment_url: str | None,
    ) -> Payment:
        payment = Payment(order_id=order_id, amount=amount, status=status, payment_url=payment_url)
        session.add(payment)
        await session.flush()
        await session.refresh(payment)
        return payment

    async def get_by_order_id(self, *, session: AsyncSession, order_id: int) -> Payment | None:
        result = await session.execute(select(Payment).where(Payment.order_id == order_id))
        return result.scalar_one_or_none()
