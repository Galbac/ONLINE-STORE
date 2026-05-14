from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.product import Product


class ProductRepository:
    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> Product | None:
        result = await session.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()

    async def count_active_by_category_id(
        self,
        *,
        session: AsyncSession,
        category_id: int,
    ) -> int:
        result = await session.execute(
            select(func.count(Product.id)).where(
                Product.category_id == category_id,
                Product.is_active.is_(True),
            ),
        )
        return int(result.scalar_one())
