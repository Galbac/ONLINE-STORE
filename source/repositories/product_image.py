from datetime import datetime

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
            .where(
                ProductImage.product_id == product_id,
                ProductImage.is_deleted.is_(False),
            )
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
        result = await session.execute(
            select(func.count(ProductImage.id)).where(
                ProductImage.product_id == product_id,
                ProductImage.is_deleted.is_(False),
            ),
        )
        return int(result.scalar_one())

    async def unset_main_by_product_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> None:
        result = await session.execute(
            select(ProductImage).where(
                ProductImage.product_id == product_id,
                ProductImage.is_deleted.is_(False),
            ),
        )
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

    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        image_id: int,
    ) -> ProductImage | None:
        result = await session.execute(
            select(ProductImage).where(
                ProductImage.id == image_id,
                ProductImage.is_deleted.is_(False),
            ),
        )
        return result.scalar_one_or_none()

    async def soft_delete(
        self,
        *,
        session: AsyncSession,
        image: ProductImage,
        deleted_at: datetime,
    ) -> ProductImage:
        image.is_deleted = True
        image.is_main = False
        image.deleted_at = deleted_at
        session.add(image)
        await session.flush()
        await session.refresh(image)
        return image

    async def get_first_active_by_product_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> ProductImage | None:
        result = await session.execute(
            select(ProductImage)
            .where(
                ProductImage.product_id == product_id,
                ProductImage.is_deleted.is_(False),
            )
            .order_by(ProductImage.sort_order.asc(), ProductImage.id.asc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def set_main(
        self,
        *,
        session: AsyncSession,
        image: ProductImage,
    ) -> ProductImage:
        image.is_main = True
        session.add(image)
        await session.flush()
        await session.refresh(image)
        return image

    async def get_by_ids(
        self,
        *,
        session: AsyncSession,
        image_ids: list[int],
    ) -> list[ProductImage]:
        if not image_ids:
            return []
        result = await session.execute(
            select(ProductImage).where(
                ProductImage.id.in_(image_ids),
                ProductImage.is_deleted.is_(False),
            ),
        )
        return list(result.scalars().all())

    async def bulk_update_sort(
        self,
        *,
        session: AsyncSession,
        images_by_id: dict[int, ProductImage],
        sort_orders_by_id: dict[int, int],
    ) -> list[ProductImage]:
        updated_images: list[ProductImage] = []
        for image_id, sort_order in sort_orders_by_id.items():
            image = images_by_id[image_id]
            image.sort_order = sort_order
            session.add(image)
            updated_images.append(image)
        await session.flush()
        return updated_images
