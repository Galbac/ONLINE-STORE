from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.order_status_history import OrderStatusHistory


class OrderStatusHistoryRepository:
    async def get_by_order_id(self, *, session: AsyncSession, order_id: int) -> list:
        result = await session.execute(
            select(OrderStatusHistory)
            .where(OrderStatusHistory.order_id == order_id)
            .order_by(desc(OrderStatusHistory.created_date)),
        )
        return list(result.scalars().all())

    async def create(self, *, session: AsyncSession, **data) -> OrderStatusHistory:
        history = OrderStatusHistory(**data)
        session.add(history)
        await session.flush()
        await session.refresh(history)
        return history
