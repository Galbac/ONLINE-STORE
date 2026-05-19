from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.product_image import ProductImage
from source.schemas.pydantic.product import ProductImageResponse


class ProductImageRepository:
    async def exists_by_file_id(self, *, session: AsyncSession, file_id: int) -> bool:
        result = await session.execute(select(ProductImage.id).where(ProductImage.file_id == file_id))
        return result.scalar_one_or_none() is not None

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

    async def count_by_product_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> int:
        result = await session.execute(select(func.count(ProductImage.id)).where(ProductImage.product_id == product_id))
        return int(result.scalar_one())

    async def unset_main_by_product_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> None:
        result = await session.execute(select(ProductImage).where(ProductImage.product_id == product_id))
        for image in result.scalars().all():
            image.is_main = False
            session.add(image)
        await session.flush()

    async def create(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        file_id: int | None,
        url: str,
        sort_order: int,
        is_main: bool,
    ) -> ProductImage:
        image = ProductImage(
            product_id=product_id,
            file_id=file_id,
            url=url,
            sort_order=sort_order,
            is_main=is_main,
        )
        session.add(image)
        await session.flush()
        await session.refresh(image)
        return image
