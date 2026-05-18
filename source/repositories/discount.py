from datetime import datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.discount import Discount
from source.db.models.product import Product
from source.schemas.pydantic.discount import ActiveDiscountsQueryParams, DiscountShortResponse


class DiscountRepository:
    async def get_active(
        self,
        *,
        session: AsyncSession,
        query: ActiveDiscountsQueryParams,
        now: datetime,
    ) -> list[DiscountShortResponse]:
        statement = self._active_statement(query=query, now=now)
        result = await session.execute(statement.order_by(Discount.starts_at.desc(), Discount.name.asc()).limit(query.limit).offset(query.offset))
        return [self._build_response(discount=discount) for discount in result.scalars().all()]

    async def count_active(
        self,
        *,
        session: AsyncSession,
        query: ActiveDiscountsQueryParams,
        now: datetime,
    ) -> int:
        subquery = self._active_statement(query=query, now=now).subquery()
        result = await session.execute(select(func.count()).select_from(subquery))
        return int(result.scalar_one())

    async def get_active_by_product_ids(
        self,
        *,
        session: AsyncSession,
        product_ids: list[int],
        now: datetime,
    ) -> list[Discount]:
        if not product_ids:
            return []
        result = await session.execute(
            select(Discount).where(
                Discount.applicable_product_id.in_(product_ids),
                Discount.is_active.is_(True),
                Discount.is_deleted.is_(False),
                or_(Discount.starts_at.is_(None), Discount.starts_at <= now),
                or_(Discount.ends_at.is_(None), Discount.ends_at >= now),
            ),
        )
        return list(result.scalars().all())

    def _active_statement(self, *, query: ActiveDiscountsQueryParams, now: datetime):
        statement = select(Discount).where(
            Discount.is_active.is_(True),
            Discount.is_deleted.is_(False),
            or_(Discount.starts_at.is_(None), Discount.starts_at <= now),
            or_(Discount.ends_at.is_(None), Discount.ends_at >= now),
        )
        if query.type is not None:
            statement = statement.where(Discount.type == query.type)
        if query.only_with_products:
            active_product_exists = exists().where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
                or_(
                    Discount.type == "cart",
                    Product.id == Discount.applicable_product_id,
                    Product.category_id == Discount.applicable_category_id,
                ),
            )
            statement = statement.where(active_product_exists)
        return statement

    def _build_response(self, *, discount: Discount) -> DiscountShortResponse:
        return DiscountShortResponse(
            id=discount.id,
            name=discount.name,
            type=discount.type,
            discount_type=discount.discount_type,
            discount_value=discount.discount_value,
            starts_at=discount.starts_at,
            ends_at=discount.ends_at,
            is_active=discount.is_active,
        )
