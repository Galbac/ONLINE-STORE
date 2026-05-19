from datetime import datetime

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.category import Category
from source.db.models.discount import Discount
from source.db.models.product import Product
from source.schemas.pydantic.product import (
    ProductCategoryShortResponse,
    ProductDetailResponse,
    ProductDiscountedQueryParams,
    ProductListQueryParams,
    ProductNewQueryParams,
    ProductPopularQueryParams,
    ProductSearchQueryParams,
    ProductSimilarQueryParams,
    ProductSeoResponse,
    ProductShortResponse,
)
from source.schemas.pydantic.admin_dashboard import (
    AdminLowStockProductResponse,
    AdminLowStockQueryParams,
    AdminPopularProductResponse,
)
from source.schemas.pydantic.discount import DiscountProductsQueryParams
from source.utils.product import build_detailed_stock_display, build_stock_display, calculate_discount_percent


class ProductRepository:
    def _low_stock_statement(self, *, category_id: int | None = None):
        statement = select(Product).where(
            Product.is_active.is_(True),
            Product.is_deleted.is_(False),
            Product.stock_quantity <= Product.min_quantity,
        )
        if category_id is not None:
            statement = statement.where(Product.category_id == category_id)
        return statement

    async def count_low_stock(self, *, session: AsyncSession, category_id: int | None = None) -> int:
        products_subquery = self._low_stock_statement(category_id=category_id).subquery()
        result = await session.execute(select(func.count()).select_from(products_subquery))
        return int(result.scalar_one())

    async def get_low_stock(
        self,
        *,
        session: AsyncSession,
        query: AdminLowStockQueryParams,
    ) -> list[AdminLowStockProductResponse]:
        result = await session.execute(
            self._low_stock_statement(category_id=query.category_id)
            .order_by(Product.stock_quantity.asc(), Product.name.asc())
            .limit(query.limit)
            .offset(query.offset),
        )
        return [
            AdminLowStockProductResponse(
                id=product.id,
                name=product.name,
                sku=product.article,
                unit=product.unit,
                product_type=product.product_type,
                stock_quantity=product.stock_quantity,
                low_stock_threshold=product.min_quantity,
                is_available=product.is_available,
            )
            for product in result.scalars().all()
        ]

    async def count_total_active(self, *, session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count(Product.id)).where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            ),
        )
        return int(result.scalar_one())

    async def get_dashboard_popular_products(
        self,
        *,
        session: AsyncSession,
        limit: int = 5,
    ) -> list[AdminPopularProductResponse]:
        result = await session.execute(
            select(Product)
            .where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            )
            .order_by(Product.popularity.desc(), Product.name.asc())
            .limit(limit),
        )
        return [
            AdminPopularProductResponse(
                id=product.id,
                name=product.name,
                price=product.price,
                popularity=product.popularity,
            )
            for product in result.scalars().all()
        ]

    def _base_statement(self, *, query: ProductListQueryParams, category_ids: set[int] | None):
        statement = (
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            )
        )
        if category_ids is not None:
            statement = statement.where(Product.category_id.in_(category_ids))
        if query.in_stock is True:
            statement = statement.where(
                Product.is_available.is_(True),
                Product.stock_quantity > 0,
            )
        elif query.in_stock is False:
            statement = statement.where(
                (Product.is_available.is_(False)) | (Product.stock_quantity <= 0),
            )
        if query.min_price is not None:
            statement = statement.where(Product.price >= query.min_price)
        if query.max_price is not None:
            statement = statement.where(Product.price <= query.max_price)
        if query.has_discount is True:
            statement = statement.where(
                Product.old_price.is_not(None),
                Product.old_price > Product.price,
            )
        elif query.has_discount is False:
            statement = statement.where(
                (Product.old_price.is_(None)) | (Product.old_price <= Product.price),
            )
        if query.product_type is not None:
            statement = statement.where(Product.product_type == query.product_type)
        return statement

    def _apply_sort(self, statement, *, sort: str | None):
        match sort:
            case "price_asc":
                return statement.order_by(Product.price.asc(), Product.name.asc())
            case "price_desc":
                return statement.order_by(Product.price.desc(), Product.name.asc())
            case "newest":
                return statement.order_by(desc(Product.created_date), Product.name.asc())
            case "popular":
                return statement.order_by(Product.popularity.desc(), Product.name.asc())
            case "name_desc":
                return statement.order_by(Product.name.desc())
            case "name_asc" | _:
                return statement.order_by(Product.name.asc())

    def _search_statement(self, *, query: ProductSearchQueryParams, category_ids: set[int] | None):
        search_pattern = f"%{query.q}%"
        statement = (
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
                or_(
                    Product.name.ilike(search_pattern),
                    Product.description.ilike(search_pattern),
                    Product.article.ilike(search_pattern),
                    Product.barcode.ilike(search_pattern),
                    Product.search_keywords.ilike(search_pattern),
                ),
            )
        )
        if category_ids is not None:
            statement = statement.where(Product.category_id.in_(category_ids))
        if query.in_stock is True:
            statement = statement.where(
                Product.is_available.is_(True),
                Product.stock_quantity > 0,
            )
        elif query.in_stock is False:
            statement = statement.where(
                (Product.is_available.is_(False)) | (Product.stock_quantity <= 0),
            )
        if query.has_discount is True:
            statement = statement.where(
                Product.old_price.is_not(None),
                Product.old_price > Product.price,
            )
        elif query.has_discount is False:
            statement = statement.where(
                (Product.old_price.is_(None)) | (Product.old_price <= Product.price),
            )
        return statement

    def _apply_search_sort(self, statement, *, query: ProductSearchQueryParams):
        match query.sort:
            case "price_asc":
                return statement.order_by(Product.price.asc(), Product.name.asc())
            case "price_desc":
                return statement.order_by(Product.price.desc(), Product.name.asc())
            case "newest":
                return statement.order_by(desc(Product.created_date), Product.name.asc())
            case "popular":
                return statement.order_by(Product.popularity.desc(), Product.name.asc())
            case "relevance" | _:
                return statement.order_by(
                    case(
                        (Product.name.ilike(f"%{query.q}%"), 0),
                        (Product.search_keywords.ilike(f"%{query.q}%"), 1),
                        (Product.description.ilike(f"%{query.q}%"), 2),
                        else_=3,
                    ),
                    Product.popularity.desc(),
                    Product.name.asc(),
                )

    def _popular_statement(self, *, query: ProductPopularQueryParams, category_ids: set[int] | None):
        statement = (
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            )
        )
        if category_ids is not None:
            statement = statement.where(Product.category_id.in_(category_ids))
        if query.in_stock:
            statement = statement.where(
                Product.is_available.is_(True),
                Product.stock_quantity > 0,
            )
        return statement

    def _discounted_statement(self, *, query: ProductDiscountedQueryParams, category_ids: set[int] | None):
        statement = (
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
                Product.old_price.is_not(None),
                Product.old_price > Product.price,
            )
        )
        if category_ids is not None:
            statement = statement.where(Product.category_id.in_(category_ids))
        if query.in_stock:
            statement = statement.where(
                Product.is_available.is_(True),
                Product.stock_quantity > 0,
            )
        return statement

    def _new_statement(
        self,
        *,
        query: ProductNewQueryParams,
        category_ids: set[int] | None,
        created_from: datetime,
    ):
        statement = (
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
                Product.created_date >= created_from,
            )
        )
        if category_ids is not None:
            statement = statement.where(Product.category_id.in_(category_ids))
        if query.in_stock:
            statement = statement.where(
                Product.is_available.is_(True),
                Product.stock_quantity > 0,
            )
        return statement

    def _apply_discounted_sort(self, statement, *, query: ProductDiscountedQueryParams):
        match query.sort:
            case "price_asc":
                return statement.order_by(Product.price.asc(), Product.name.asc())
            case "price_desc":
                return statement.order_by(Product.price.desc(), Product.name.asc())
            case "newest":
                return statement.order_by(desc(Product.created_date), Product.name.asc())
            case "discount_desc" | _:
                return statement.order_by(
                    ((Product.old_price - Product.price) / Product.old_price).desc(),
                    Product.name.asc(),
                )

    async def get_active_list(
        self,
        *,
        session: AsyncSession,
        query: ProductListQueryParams,
        category_ids: set[int] | None = None,
    ) -> list[ProductShortResponse]:
        statement = (
            self._apply_sort(self._base_statement(query=query, category_ids=category_ids), sort=query.sort)
            .limit(query.limit)
            .offset(query.offset)
        )
        result = await session.execute(statement)
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def count_active(
        self,
        *,
        session: AsyncSession,
        query: ProductListQueryParams,
        category_ids: set[int] | None = None,
    ) -> int:
        products_subquery = self._base_statement(query=query, category_ids=category_ids).subquery()
        result = await session.execute(select(func.count()).select_from(products_subquery))
        return int(result.scalar_one())

    async def search_active(
        self,
        *,
        session: AsyncSession,
        query: ProductSearchQueryParams,
        category_ids: set[int] | None = None,
    ) -> list[ProductShortResponse]:
        statement = (
            self._apply_search_sort(self._search_statement(query=query, category_ids=category_ids), query=query)
            .limit(query.limit)
            .offset(query.offset)
        )
        result = await session.execute(statement)
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def count_search_active(
        self,
        *,
        session: AsyncSession,
        query: ProductSearchQueryParams,
        category_ids: set[int] | None = None,
    ) -> int:
        products_subquery = self._search_statement(query=query, category_ids=category_ids).subquery()
        result = await session.execute(select(func.count()).select_from(products_subquery))
        return int(result.scalar_one())

    async def get_popular_active(
        self,
        *,
        session: AsyncSession,
        query: ProductPopularQueryParams,
        category_ids: set[int] | None = None,
    ) -> list[ProductShortResponse]:
        result = await session.execute(
            self._popular_statement(query=query, category_ids=category_ids)
            .order_by(Product.popularity.desc(), Product.name.asc())
            .limit(query.limit),
        )
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def get_discounted_active(
        self,
        *,
        session: AsyncSession,
        query: ProductDiscountedQueryParams,
        category_ids: set[int] | None = None,
    ) -> list[ProductShortResponse]:
        statement = (
            self._apply_discounted_sort(
                self._discounted_statement(query=query, category_ids=category_ids),
                query=query,
            )
            .limit(query.limit)
            .offset(query.offset)
        )
        result = await session.execute(statement)
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def count_discounted_active(
        self,
        *,
        session: AsyncSession,
        query: ProductDiscountedQueryParams,
        category_ids: set[int] | None = None,
    ) -> int:
        products_subquery = self._discounted_statement(query=query, category_ids=category_ids).subquery()
        result = await session.execute(select(func.count()).select_from(products_subquery))
        return int(result.scalar_one())

    async def get_discounted_products(
        self,
        *,
        session: AsyncSession,
        query: DiscountProductsQueryParams,
    ) -> list[ProductShortResponse]:
        statement = (
            self._apply_discounted_sort(
                self._discount_products_statement(query=query),
                query=query,
            )
            .limit(query.limit)
            .offset(query.offset)
        )
        result = await session.execute(statement)
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def count_discounted_products(
        self,
        *,
        session: AsyncSession,
        query: DiscountProductsQueryParams,
    ) -> int:
        products_subquery = self._discount_products_statement(query=query).subquery()
        result = await session.execute(select(func.count()).select_from(products_subquery))
        return int(result.scalar_one())

    def _discount_products_statement(self, *, query: DiscountProductsQueryParams):
        now = datetime.now(settings.tz)
        active_discount_exists = (
            select(Discount.id)
            .where(
                Discount.is_active.is_(True),
                Discount.is_deleted.is_(False),
                or_(Discount.starts_at.is_(None), Discount.starts_at <= now),
                or_(Discount.ends_at.is_(None), Discount.ends_at >= now),
                or_(
                    Discount.type == "cart",
                    Discount.applicable_product_id == Product.id,
                    Discount.applicable_category_id == Product.category_id,
                ),
            )
            .exists()
        )
        statement = (
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
                Product.old_price.is_not(None),
                Product.old_price > Product.price,
                active_discount_exists,
            )
        )
        if query.category_id is not None:
            statement = statement.where(Product.category_id == query.category_id)
        if query.in_stock:
            statement = statement.where(Product.is_available.is_(True), Product.stock_quantity > 0)
        return statement

    async def get_new_active(
        self,
        *,
        session: AsyncSession,
        query: ProductNewQueryParams,
        created_from: datetime,
        category_ids: set[int] | None = None,
    ) -> list[ProductShortResponse]:
        result = await session.execute(
            self._new_statement(query=query, category_ids=category_ids, created_from=created_from)
            .order_by(desc(Product.created_date), Product.name.asc())
            .limit(query.limit),
        )
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def get_by_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> Product | None:
        result = await session.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()

    async def get_by_ids(
        self,
        *,
        session: AsyncSession,
        product_ids: list[int],
    ) -> list[Product]:
        if not product_ids:
            return []
        result = await session.execute(select(Product).where(Product.id.in_(product_ids)))
        return list(result.scalars().all())

    async def release_stock(self, *, session: AsyncSession, products_by_id: dict[int, Product], order_items: list) -> list[Product]:
        products: list[Product] = []
        for item in order_items:
            product = products_by_id.get(item.product_id)
            if product is None:
                continue
            product.stock_quantity += item.quantity
            session.add(product)
            products.append(product)
        await session.flush()
        return products

    async def get_active_by_id(
        self,
        *,
        session: AsyncSession,
        product_id: int,
    ) -> ProductDetailResponse | None:
        result = await session.execute(
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.id == product_id,
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            ),
        )
        row = result.one_or_none()
        if row is None:
            return None
        product, category = row
        return self._build_product_detail_response(product=product, category=category)

    async def get_active_by_slug(
        self,
        *,
        session: AsyncSession,
        slug: str,
    ) -> ProductDetailResponse | None:
        result = await session.execute(
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.slug == slug,
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            ),
        )
        row = result.one_or_none()
        if row is None:
            return None
        product, category = row
        return self._build_product_detail_response(product=product, category=category)

    async def get_similar_active(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        category_id: int | None,
        limit: int = 4,
    ) -> list[ProductShortResponse]:
        statement = (
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.id != product_id,
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            )
            .order_by(Product.popularity.desc(), Product.name.asc())
            .limit(limit)
        )
        if category_id is not None:
            statement = statement.where(Product.category_id == category_id)
        result = await session.execute(statement)
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def get_similar_by_category(
        self,
        *,
        session: AsyncSession,
        product_id: int,
        category_id: int | None,
        query: ProductSimilarQueryParams,
    ) -> list[ProductShortResponse]:
        statement = (
            select(Product, Category)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Product.id != product_id,
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            )
            .order_by(Product.popularity.desc(), desc(Product.created_date), Product.name.asc())
            .limit(query.limit)
        )
        if category_id is not None:
            statement = statement.where(Product.category_id == category_id)
        if query.in_stock:
            statement = statement.where(
                Product.is_available.is_(True),
                Product.stock_quantity > 0,
            )
        result = await session.execute(statement)
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def count_active_by_category_id(
        self,
        *,
        session: AsyncSession,
        category_id: int,
    ) -> int:
        result = await session.execute(
            select(func.count(Product.id)).where(
                Product.category_id == category_id,
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            ),
        )
        return int(result.scalar_one())

    async def count_active_grouped_by_category(self, *, session: AsyncSession) -> dict[int, int]:
        result = await session.execute(
            select(Product.category_id, func.count(Product.id))
            .where(
                Product.category_id.is_not(None),
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            )
            .group_by(Product.category_id),
        )
        return {
            int(category_id): int(products_count)
            for category_id, products_count in result.all()
        }

    def _build_product_response(self, *, product: Product, category: Category | None) -> ProductShortResponse:
        product_category = None
        if category is not None:
            product_category = ProductCategoryShortResponse(
                id=category.id,
                name=category.name,
                slug=category.slug,
            )
        return ProductShortResponse(
            id=product.id,
            name=product.name,
            slug=product.slug,
            preview_image_url=product.preview_image_url,
            price=product.price,
            old_price=product.old_price,
            discount_percent=calculate_discount_percent(price=product.price, old_price=product.old_price),
            unit=product.unit,
            product_type=product.product_type,
            is_available=product.is_available,
            stock_display=build_stock_display(
                is_available=product.is_available,
                stock_quantity=product.stock_quantity,
            ),
            category=product_category,
            created_at=product.created_date,
        )

    def _build_product_detail_response(self, *, product: Product, category: Category | None) -> ProductDetailResponse:
        product_category = None
        if category is not None:
            product_category = ProductCategoryShortResponse(
                id=category.id,
                name=category.name,
                slug=category.slug,
            )
        seo = None
        if product.meta_title is not None or product.meta_description is not None:
            seo = ProductSeoResponse(
                meta_title=product.meta_title,
                meta_description=product.meta_description,
            )
        return ProductDetailResponse(
            id=product.id,
            name=product.name,
            slug=product.slug,
            description=product.description,
            category=product_category,
            price=product.price,
            old_price=product.old_price,
            discount_percent=calculate_discount_percent(price=product.price, old_price=product.old_price),
            unit=product.unit,
            product_type=product.product_type,
            quantity_step=product.quantity_step,
            min_quantity=product.min_quantity,
            is_available=product.is_available,
            stock_quantity=product.stock_quantity,
            stock_display=build_detailed_stock_display(
                is_available=product.is_available,
                stock_quantity=product.stock_quantity,
                unit=product.unit,
            ),
            images=[],
            seo=seo,
        )
