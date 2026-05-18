from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.refund import Refund


class RefundRepository:
    async def create(
        self,
        *,
        session: AsyncSession,
        payment_id: int,
        amount: Decimal,
        currency: str,
        status: str,
        reason: str | None,
        provider_refund_id: str | None,
    ) -> Refund:
        refund = Refund(
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            status=status,
            reason=reason,
            provider_refund_id=provider_refund_id,
        )
        session.add(refund)
        await session.flush()
        await session.refresh(refund)
        return refund

    async def sum_refunded_by_payment_id(self, *, session: AsyncSession, payment_id: int) -> Decimal:
        result = await session.execute(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                Refund.payment_id == payment_id,
                Refund.status.in_(("pending", "succeeded")),
            ),
        )
        return Decimal(result.scalar_one())
