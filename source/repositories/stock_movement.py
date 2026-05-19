from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.stock_movement import StockMovement


class StockMovementRepository:
    async def create(self, *, session: AsyncSession, **data) -> StockMovement:
        movement = StockMovement(**data)
        session.add(movement)
        await session.flush()
        await session.refresh(movement)
        return movement
