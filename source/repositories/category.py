from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.category import Category
from source.db.models.product import Product
from source.schemas.pydantic.category import (
    CategoryBreadcrumbResponse,
    CategoryDetailResponse,
    CategoryListQueryParams,
    CategorySeoResponse,
    CategoryShortResponse,
)
from source.schemas.pydantic.admin_category import AdminCategoryListQueryParams


class CategoryRepository:
    async def exists_by_image_file_id(self, *, session: AsyncSession, file_id: int) -> bool:
        result = await session.execute(select(Category.id).where(Category.image_file_id == file_id))
        return result.scalar_one_or_none() is not None

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

    def _admin_statement(self, *, query: AdminCategoryListQueryParams):
        statement = select(Category)
        if not query.include_deleted:
            statement = statement.where(Category.is_deleted.is_(False))
        if query.q is not None:
            search_pattern = f"%{query.q}%"
            statement = statement.where(
                or_(
                    Category.name.ilike(search_pattern),
                    Category.slug.ilike(search_pattern),
                ),
            )
        if query.parent_id is not None:
            statement = statement.where(Category.parent_id == query.parent_id)
        if query.is_active is not None:
            statement = statement.where(Category.is_active.is_(query.is_active))
        return statement

    async def admin_get_list(
        self,
        *,
        session: AsyncSession,
        query: AdminCategoryListQueryParams,
    ) -> list[Category]:
        result = await session.execute(
            self._admin_statement(query=query)
            .order_by(Category.sort_order.asc(), Category.name.asc())
            .limit(query.limit)
            .offset(query.offset),
        )
        return list(result.scalars().all())

    async def admin_count(
        self,
        *,
        session: AsyncSession,
        query: AdminCategoryListQueryParams,
    ) -> int:
        categories_subquery = self._admin_statement(query=query).subquery()
        result = await session.execute(select(func.count()).select_from(categories_subquery))
        return int(result.scalar_one())

    async def get_active_all(
        self,
        *,
        session: AsyncSession,
    ) -> list[CategoryShortResponse]:
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
            .order_by(Category.sort_order.asc(), Category.name.asc())
        )
        result = await session.execute(statement)
        return [
            self._build_category_response(category=category, products_count=products_count)
            for category, products_count in result.all()
        ]

    async def get_active_by_id(
        self,
        *,
        session: AsyncSession,
        category_id: int,
    ) -> CategoryDetailResponse | None:
        result = await session.execute(
            select(Category)
            .where(
                Category.id == category_id,
                Category.is_active.is_(True),
                Category.is_deleted.is_(False),
            )
        )
        category = result.scalar_one_or_none()
        if category is None:
            return None
        return self._build_category_detail_response(category=category)

    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        category_id: int,
    ) -> Category | None:
        result = await session.execute(
            select(Category).where(
                Category.id == category_id,
                Category.is_deleted.is_(False),
            ),
        )
        return result.scalar_one_or_none()

    async def get_active_by_slug(
        self,
        *,
        session: AsyncSession,
        slug: str,
    ) -> CategoryDetailResponse | None:
        result = await session.execute(
            select(Category)
            .where(
                Category.slug == slug,
                Category.is_active.is_(True),
                Category.is_deleted.is_(False),
            )
        )
        category = result.scalar_one_or_none()
        if category is None:
            return None
        return self._build_category_detail_response(category=category)

    async def get_active_children(
        self,
        *,
        session: AsyncSession,
        parent_id: int,
    ) -> list[CategoryShortResponse]:
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
                Category.parent_id == parent_id,
                Category.is_active.is_(True),
                Category.is_deleted.is_(False),
            )
            .group_by(Category.id)
            .order_by(Category.sort_order.asc(), Category.name.asc())
        )
        result = await session.execute(statement)
        return [
            self._build_category_response(category=category, products_count=products_count)
            for category, products_count in result.all()
        ]

    async def get_parent_chain(
        self,
        *,
        session: AsyncSession,
        category_id: int,
    ) -> list[CategoryBreadcrumbResponse]:
        result = await session.execute(
            select(Category).where(
                Category.is_active.is_(True),
                Category.is_deleted.is_(False),
            ),
        )
        categories_by_id = {
            category.id: category
            for category in result.scalars().all()
        }
        breadcrumbs: list[CategoryBreadcrumbResponse] = []
        current_category = categories_by_id.get(category_id)
        while current_category is not None:
            breadcrumbs.append(
                CategoryBreadcrumbResponse(
                    id=current_category.id,
                    name=current_category.name,
                    slug=current_category.slug,
                ),
            )
            current_category = categories_by_id.get(current_category.parent_id)
        return list(reversed(breadcrumbs))

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

    def _build_category_detail_response(self, *, category: Category) -> CategoryDetailResponse:
        seo = None
        if category.meta_title is not None or category.meta_description is not None:
            seo = CategorySeoResponse(
                meta_title=category.meta_title,
                meta_description=category.meta_description,
            )
        return CategoryDetailResponse(
            id=category.id,
            name=category.name,
            slug=category.slug,
            description=category.description,
            parent_id=category.parent_id,
            image_url=category.image_url,
            sort_order=category.sort_order,
            seo=seo,
        )
