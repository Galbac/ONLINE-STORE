from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.category import Category
from source.db.models.product import Product
from source.schemas.pydantic.category import CategoryListQueryParams, CategoryShortResponse


class CategoryRepository:
    def _base_statement(self, *, query: CategoryListQueryParams):
        active_products_count = func.count(Product.id).label("products_count")
        statement = (
            select(Category, active_products_count)
            .outerjoin(
                Product,
                and_(
                    Product.category_id == Category.id,
                    Product.is_active.is_(True),
                ),
            )
            .where(
                Category.is_active.is_(True),
                Category.is_deleted.is_(False),
            )
            .group_by(Category.id)
        )
        if query.parent_id is not None:
            statement = statement.where(Category.parent_id == query.parent_id)
        elif query.only_root:
            statement = statement.where(Category.parent_id.is_(None))
        if not query.include_empty:
            statement = statement.having(active_products_count > 0)
        return statement

    async def get_active_list(
        self,
        *,
        session: AsyncSession,
        query: CategoryListQueryParams,
    ) -> list[CategoryShortResponse]:
        statement = (
            self._base_statement(query=query)
            .order_by(Category.sort_order.asc(), Category.name.asc())
            .limit(query.limit)
            .offset(query.offset)
        )
        result = await session.execute(statement)
        return [
            self._build_category_response(category=category, products_count=products_count)
            for category, products_count in result.all()
        ]

    async def count_active(
        self,
        *,
        session: AsyncSession,
        query: CategoryListQueryParams,
    ) -> int:
        categories_subquery = self._base_statement(query=query).subquery()
        result = await session.execute(select(func.count()).select_from(categories_subquery))
        return int(result.scalar_one())

    def _build_category_response(self, *, category: Category, products_count: int) -> CategoryShortResponse:
        return CategoryShortResponse(
            id=category.id,
            name=category.name,
            slug=category.slug,
            parent_id=category.parent_id,
            image_url=category.image_url,
            sort_order=category.sort_order,
            products_count=int(products_count),
        )
