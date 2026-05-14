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

    async def count_active_grouped_by_category(self, *, session: AsyncSession) -> dict[int, int]:
        result = await session.execute(
            select(Product.category_id, func.count(Product.id))
            .where(
                Product.category_id.is_not(None),
                Product.is_active.is_(True),
            )
            .group_by(Product.category_id),
        )
        return {
            int(category_id): int(products_count)
            for category_id, products_count in result.all()
        }
