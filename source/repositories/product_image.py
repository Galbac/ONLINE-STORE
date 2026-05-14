from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.product_image import ProductImage
from source.schemas.pydantic.product import ProductImageResponse


class ProductImageRepository:
    async def get_by_product_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> list[ProductImageResponse]:
        result = await session.execute(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.sort_order.asc(), ProductImage.id.asc()),
        )
        return [
            ProductImageResponse(
                id=image.id,
                url=image.url,
                sort_order=image.sort_order,
            )
            for image in result.scalars().all()
        ]
