from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from source.db.models.product_review import ProductReview


class ProductReviewRepository:
    async def get_by_product(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        is_approved: bool = True,
    ) -> list[ProductReview]:
        stmt = (
            select(ProductReview)
            .options(joinedload(ProductReview.user))
            .where(
                ProductReview.product_id == product_id,
                ProductReview.is_approved.is_(is_approved),
            )
            .order_by(desc(ProductReview.created_date))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(
        self,
        *,
        session: AsyncSession,
        is_approved: bool | None = None,
    ) -> list[ProductReview]:
        stmt = select(ProductReview).options(joinedload(ProductReview.user))
        if is_approved is not None:
            stmt = stmt.where(ProductReview.is_approved.is_(is_approved))
        stmt = stmt.order_by(desc(ProductReview.created_date))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, *, session: AsyncSession, review_id: int) -> ProductReview | None:
        stmt = (
            select(ProductReview)
            .options(joinedload(ProductReview.user))
            .where(ProductReview.id == review_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, *, session: AsyncSession, **kwargs) -> ProductReview:
        review = ProductReview(**kwargs)
        session.add(review)
        await session.flush()
        await session.refresh(review)
        return review

    async def update(self, *, session: AsyncSession, review: ProductReview, **kwargs) -> ProductReview:
        for key, value in kwargs.items():
            if value is not None:
                setattr(review, key, value)
        session.add(review)
        await session.flush()
        await session.refresh(review)
        return review
