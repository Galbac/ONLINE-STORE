from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.order_item import OrderItem


class OrderItemRepository:
    async def get_by_order_id(
        self,
        *,
        session: AsyncSession,
        order_id: int,
    ) -> list[OrderItem]:
        result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
        return list(result.scalars().all())
