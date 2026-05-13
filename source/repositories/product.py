from sqlalchemy import select
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
