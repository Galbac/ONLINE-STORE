from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

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
