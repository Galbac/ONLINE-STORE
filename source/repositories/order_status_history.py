from sqlalchemy.ext.asyncio import AsyncSession


class OrderStatusHistoryRepository:
    async def get_by_order_id(self, *, session: AsyncSession, order_id: int) -> list:
        return []
