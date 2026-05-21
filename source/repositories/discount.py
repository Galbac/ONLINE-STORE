from datetime import datetime, time

from sqlalchemy import delete, desc, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.discount import Discount, DiscountCategory, DiscountProduct
from source.db.models.category import Category
from source.db.models.product import Product
from source.schemas.pydantic.discount import ActiveDiscountsQueryParams, AdminDiscountListQueryParams, DiscountShortResponse


class DiscountRepository:
    async def create(
        self,
        *,
        session: AsyncSession,
        **data,
    ) -> Discount:
        discount = Discount(**data)
        session.add(discount)
        await session.flush()
        await session.refresh(discount)
        return discount

    async def admin_get_list(
        self,
        *,
        session: AsyncSession,
        query: AdminDiscountListQueryParams,
    ) -> list[Discount]:
        statement = self._admin_statement(query=query)
        result = await session.execute(
            statement.order_by(desc(Discount.created_date), desc(Discount.id)).limit(query.limit).offset(query.offset),
        )
        return list(result.scalars().all())

    async def admin_count(
        self,
        *,
        session: AsyncSession,
        query: AdminDiscountListQueryParams,
    ) -> int:
        subquery = self._admin_statement(query=query).subquery()
        result = await session.execute(select(func.count()).select_from(subquery))
        return int(result.scalar_one())

    async def admin_get_by_id(
        self,
        *,
        session: AsyncSession,
        discount_id: int,
    ) -> Discount | None:
        result = await session.execute(
            select(Discount).where(
                Discount.id == discount_id,
                Discount.is_deleted.is_(False),
            ),
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        *,
        session: AsyncSession,
        discount: Discount,
        data: dict,
    ) -> Discount:
        for field, value in data.items():
            setattr(discount, field, value)
        session.add(discount)
        await session.flush()
        await session.refresh(discount)
        return discount

    async def soft_delete(
        self,
        *,
        session: AsyncSession,
        discount: Discount,
        deleted_at: datetime,
        deleted_by: int,
    ) -> Discount:
        discount.is_deleted = True
        discount.is_active = False
        discount.deleted_at = deleted_at
        discount.deleted_by = deleted_by
        session.add(discount)
        await session.flush()
        await session.refresh(discount)
        return discount

    async def has_conflicts(
        self,
        *,
        session: AsyncSession,
        discount_id: int | None,
        type: str,
        product_ids: list[int],
        category_ids: list[int],
        starts_at: datetime | None,
        ends_at: datetime | None,
        is_active: bool,
    ) -> bool:
        if not is_active:
            return False

        statement = select(Discount.id).where(
            Discount.is_deleted.is_(False),
            Discount.is_active.is_(True),
            Discount.type == type,
        )
        if discount_id is not None:
            statement = statement.where(Discount.id != discount_id)
        if starts_at is not None:
            statement = statement.where(or_(Discount.ends_at.is_(None), Discount.ends_at > starts_at))
        if ends_at is not None:
            statement = statement.where(or_(Discount.starts_at.is_(None), Discount.starts_at < ends_at))

        if type == "product":
            if not product_ids:
                return False
            relation_exists = exists().where(
                DiscountProduct.discount_id == Discount.id,
                DiscountProduct.product_id.in_(product_ids),
            )
            statement = statement.where(or_(Discount.applicable_product_id.in_(product_ids), relation_exists))
        elif type == "category":
            if not category_ids:
                return False
            relation_exists = exists().where(
                DiscountCategory.discount_id == Discount.id,
                DiscountCategory.category_id.in_(category_ids),
            )
            statement = statement.where(or_(Discount.applicable_category_id.in_(category_ids), relation_exists))
        elif type != "cart":
            return False

        result = await session.execute(statement.limit(1))
        return result.scalar_one_or_none() is not None

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

    def _admin_statement(self, *, query: AdminDiscountListQueryParams):
        statement = select(Discount).where(Discount.is_deleted.is_(False))
        if query.q is not None:
            statement = statement.where(Discount.name.ilike(f"%{query.q}%"))
        if query.type is not None:
            statement = statement.where(Discount.type == query.type)
        if query.discount_type is not None:
            statement = statement.where(Discount.discount_type == query.discount_type)
        if query.is_active is not None:
            statement = statement.where(Discount.is_active.is_(query.is_active))
        if query.date_from is not None:
            statement = statement.where(Discount.created_date >= datetime.combine(query.date_from, time.min))
        if query.date_to is not None:
            statement = statement.where(Discount.created_date <= datetime.combine(query.date_to, time.max))
        return statement

    async def get_by_product_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> list[Discount]:
        result = await session.execute(
            select(Discount)
            .where(
                Discount.applicable_product_id == product_id,
                Discount.is_deleted.is_(False),
            )
            .order_by(Discount.created_date.desc(), Discount.id.desc()),
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


class DiscountProductRepository:
    async def bulk_create(self, *, session: AsyncSession, discount_id: int, product_ids: list[int]) -> list[DiscountProduct]:
        relations = [
            DiscountProduct(discount_id=discount_id, product_id=product_id)
            for product_id in product_ids
        ]
        session.add_all(relations)
        await session.flush()
        return relations

    async def get_products(self, *, session: AsyncSession, discount_id: int) -> list[Product]:
        result = await session.execute(
            select(Product)
            .join(DiscountProduct, DiscountProduct.product_id == Product.id)
            .where(
                DiscountProduct.discount_id == discount_id,
                Product.is_deleted.is_(False),
            )
            .order_by(Product.name.asc(), Product.id.asc()),
        )
        return list(result.scalars().all())

    async def replace_products(self, *, session: AsyncSession, discount_id: int, product_ids: list[int]) -> list[DiscountProduct]:
        await session.execute(delete(DiscountProduct).where(DiscountProduct.discount_id == discount_id))
        if not product_ids:
            await session.flush()
            return []
        return await self.bulk_create(session=session, discount_id=discount_id, product_ids=product_ids)


class DiscountCategoryRepository:
    async def bulk_create(self, *, session: AsyncSession, discount_id: int, category_ids: list[int]) -> list[DiscountCategory]:
        relations = [
            DiscountCategory(discount_id=discount_id, category_id=category_id)
            for category_id in category_ids
        ]
        session.add_all(relations)
        await session.flush()
        return relations

    async def get_categories(self, *, session: AsyncSession, discount_id: int) -> list[Category]:
        result = await session.execute(
            select(Category)
            .join(DiscountCategory, DiscountCategory.category_id == Category.id)
            .where(
                DiscountCategory.discount_id == discount_id,
                Category.is_deleted.is_(False),
            )
            .order_by(Category.name.asc(), Category.id.asc()),
        )
        return list(result.scalars().all())

    async def replace_categories(self, *, session: AsyncSession, discount_id: int, category_ids: list[int]) -> list[DiscountCategory]:
        await session.execute(delete(DiscountCategory).where(DiscountCategory.discount_id == discount_id))
        if not category_ids:
            await session.flush()
            return []
        return await self.bulk_create(session=session, discount_id=discount_id, category_ids=category_ids)
