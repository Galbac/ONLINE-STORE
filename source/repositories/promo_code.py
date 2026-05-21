from datetime import datetime, time

from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.category import Category
from source.db.models.promo_code import PromoCode, PromoCodeCategory, PromoCodeProduct, PromoCodeUsage
from source.db.models.product import Product
from source.schemas.pydantic.promo_code import AdminPromoCodeListQueryParams


class PromoCodeRepository:
    async def create(
        self,
        *,
        session: AsyncSession,
        **data,
    ) -> PromoCode:
        promo_code = PromoCode(**data)
        session.add(promo_code)
        await session.flush()
        await session.refresh(promo_code)
        return promo_code

    async def update(
        self,
        *,
        session: AsyncSession,
        promo_code: PromoCode,
        data: dict,
    ) -> PromoCode:
        for field, value in data.items():
            setattr(promo_code, field, value)
        session.add(promo_code)
        await session.flush()
        await session.refresh(promo_code)
        return promo_code

    async def soft_delete(
        self,
        *,
        session: AsyncSession,
        promo_code: PromoCode,
        deleted_at: datetime,
        deleted_by: int,
    ) -> PromoCode:
        promo_code.is_deleted = True
        promo_code.is_active = False
        promo_code.deleted_at = deleted_at
        promo_code.deleted_by = deleted_by
        session.add(promo_code)
        await session.flush()
        await session.refresh(promo_code)
        return promo_code

    async def admin_get_list(
        self,
        *,
        session: AsyncSession,
        query: AdminPromoCodeListQueryParams,
    ) -> list[PromoCode]:
        statement = self._admin_statement(query=query)
        result = await session.execute(
            statement.order_by(desc(PromoCode.created_date), desc(PromoCode.id)).limit(query.limit).offset(query.offset),
        )
        return list(result.scalars().all())

    async def admin_count(
        self,
        *,
        session: AsyncSession,
        query: AdminPromoCodeListQueryParams,
    ) -> int:
        subquery = self._admin_statement(query=query).subquery()
        result = await session.execute(select(func.count()).select_from(subquery))
        return int(result.scalar_one())

    async def admin_get_by_id(self, *, session: AsyncSession, promo_code_id: int) -> PromoCode | None:
        result = await session.execute(
            select(PromoCode).where(
                PromoCode.id == promo_code_id,
                PromoCode.is_deleted.is_(False),
            ),
        )
        return result.scalar_one_or_none()

    def _admin_statement(self, *, query: AdminPromoCodeListQueryParams):
        statement = select(PromoCode).where(PromoCode.is_deleted.is_(False))
        if query.q is not None:
            statement = statement.where(
                or_(
                    PromoCode.code.ilike(f"%{query.q}%"),
                    PromoCode.name.ilike(f"%{query.q}%"),
                ),
            )
        if query.is_active is not None:
            statement = statement.where(PromoCode.is_active.is_(query.is_active))
        if query.discount_type is not None:
            statement = statement.where(PromoCode.discount_type == query.discount_type)
        if query.date_from is not None:
            statement = statement.where(PromoCode.created_date >= datetime.combine(query.date_from, time.min))
        if query.date_to is not None:
            statement = statement.where(PromoCode.created_date <= datetime.combine(query.date_to, time.max))
        return statement

    async def get_by_id(self, *, session: AsyncSession, promo_code_id: int) -> PromoCode | None:
        result = await session.execute(select(PromoCode).where(PromoCode.id == promo_code_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, *, session: AsyncSession, code: str) -> PromoCode | None:
        result = await session.execute(select(PromoCode).where(PromoCode.code == code))
        return result.scalar_one_or_none()

    async def get_active_by_code(self, *, session: AsyncSession, code: str) -> PromoCode | None:
        result = await session.execute(
            select(PromoCode).where(
                PromoCode.code == code,
                PromoCode.is_active.is_(True),
                PromoCode.is_deleted.is_(False),
            ),
        )
        return result.scalar_one_or_none()


class PromoCodeUsageRepository:
    async def count_by_promo_code_id(self, *, session: AsyncSession, promo_code_id: int) -> int:
        result = await session.execute(
            select(func.count(PromoCodeUsage.id)).where(PromoCodeUsage.promo_code_id == promo_code_id),
        )
        return int(result.scalar_one())

    async def count_grouped_by_promo_code_ids(
        self,
        *,
        session: AsyncSession,
        promo_code_ids: list[int],
    ) -> dict[int, int]:
        if not promo_code_ids:
            return {}
        result = await session.execute(
            select(PromoCodeUsage.promo_code_id, func.count(PromoCodeUsage.id))
            .where(PromoCodeUsage.promo_code_id.in_(promo_code_ids))
            .group_by(PromoCodeUsage.promo_code_id),
        )
        return {promo_code_id: count for promo_code_id, count in result.all()}

    async def count_by_code(self, *, session: AsyncSession, promo_code_id: int) -> int:
        result = await session.execute(
            select(func.count(PromoCodeUsage.id)).where(PromoCodeUsage.promo_code_id == promo_code_id),
        )
        return result.scalar_one()

    async def count_by_user_and_code(self, *, session: AsyncSession, user_id: int, promo_code_id: int) -> int:
        result = await session.execute(
            select(func.count(PromoCodeUsage.id)).where(
                PromoCodeUsage.user_id == user_id,
                PromoCodeUsage.promo_code_id == promo_code_id,
            ),
        )
        return result.scalar_one()

    async def create(
        self,
        *,
        session: AsyncSession,
        promo_code_id: int,
        user_id: int,
        order_id: int | None = None,
        status: str = "reserved",
    ) -> PromoCodeUsage:
        usage = PromoCodeUsage(promo_code_id=promo_code_id, user_id=user_id, order_id=order_id, status=status)
        session.add(usage)
        await session.flush()
        await session.refresh(usage)
        return usage

    async def cancel_by_order_id(self, *, session: AsyncSession, order_id: int) -> None:
        result = await session.execute(select(PromoCodeUsage).where(PromoCodeUsage.order_id == order_id))
        usage = result.scalar_one_or_none()
        if usage is not None:
            usage.status = "cancelled"
            session.add(usage)
            await session.flush()


class PromoCodeProductRepository:
    async def bulk_create(self, *, session: AsyncSession, promo_code_id: int, product_ids: list[int]) -> list[PromoCodeProduct]:
        relations = [
            PromoCodeProduct(promo_code_id=promo_code_id, product_id=product_id)
            for product_id in product_ids
        ]
        session.add_all(relations)
        await session.flush()
        return relations

    async def get_products(self, *, session: AsyncSession, promo_code_id: int) -> list[Product]:
        result = await session.execute(
            select(Product)
            .join(PromoCodeProduct, PromoCodeProduct.product_id == Product.id)
            .where(
                PromoCodeProduct.promo_code_id == promo_code_id,
                Product.is_deleted.is_(False),
            )
            .order_by(Product.name.asc(), Product.id.asc()),
        )
        return list(result.scalars().all())

    async def replace_products(self, *, session: AsyncSession, promo_code_id: int, product_ids: list[int]) -> list[PromoCodeProduct]:
        await session.execute(delete(PromoCodeProduct).where(PromoCodeProduct.promo_code_id == promo_code_id))
        if not product_ids:
            await session.flush()
            return []
        return await self.bulk_create(session=session, promo_code_id=promo_code_id, product_ids=product_ids)


class PromoCodeCategoryRepository:
    async def bulk_create(self, *, session: AsyncSession, promo_code_id: int, category_ids: list[int]) -> list[PromoCodeCategory]:
        relations = [
            PromoCodeCategory(promo_code_id=promo_code_id, category_id=category_id)
            for category_id in category_ids
        ]
        session.add_all(relations)
        await session.flush()
        return relations

    async def get_categories(self, *, session: AsyncSession, promo_code_id: int) -> list[Category]:
        result = await session.execute(
            select(Category)
            .join(PromoCodeCategory, PromoCodeCategory.category_id == Category.id)
            .where(
                PromoCodeCategory.promo_code_id == promo_code_id,
                Category.is_deleted.is_(False),
            )
            .order_by(Category.name.asc(), Category.id.asc()),
        )
        return list(result.scalars().all())

    async def replace_categories(self, *, session: AsyncSession, promo_code_id: int, category_ids: list[int]) -> list[PromoCodeCategory]:
        await session.execute(delete(PromoCodeCategory).where(PromoCodeCategory.promo_code_id == promo_code_id))
        if not category_ids:
            await session.flush()
            return []
        return await self.bulk_create(session=session, promo_code_id=promo_code_id, category_ids=category_ids)
