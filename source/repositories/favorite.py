from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.category import Category
from source.db.models.favorite import Favorite
from source.db.models.product import Product
from source.schemas.pydantic.favorite import FavoriteProductResponse, FavoritesQueryParams
from source.schemas.pydantic.product import ProductCategoryShortResponse
from source.utils.product import build_stock_display, calculate_discount_percent


class FavoriteRepository:
    async def exists(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        product_id: int,
    ) -> bool:
        result = await session.execute(
            select(Favorite.id).where(
                Favorite.user_id == user_id,
                Favorite.product_id == product_id,
            ),
        )
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        product_id: int,
    ) -> Favorite:
        favorite = Favorite(user_id=user_id, product_id=product_id)
        session.add(favorite)
        await session.flush()
        return favorite

    async def get_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        query: FavoritesQueryParams,
    ) -> list[FavoriteProductResponse]:
        statement = (
            self._base_statement(user_id=user_id)
            .order_by(Favorite.created_date.desc())
            .limit(query.limit)
            .offset(query.offset)
        )
        result = await session.execute(statement)
        return [
            self._build_product_response(product=product, category=category)
            for product, category in result.all()
        ]

    async def count_by_user_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> int:
        subquery = self._base_statement(user_id=user_id).subquery()
        result = await session.execute(select(func.count()).select_from(subquery))
        return int(result.scalar_one())

    def _base_statement(self, *, user_id: int):
        return (
            select(Product, Category)
            .join(Favorite, Favorite.product_id == Product.id)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(
                Favorite.user_id == user_id,
                Product.is_active.is_(True),
                Product.is_deleted.is_(False),
            )
        )

    def _build_product_response(self, *, product: Product, category: Category | None) -> FavoriteProductResponse:
        product_category = None
        if category is not None:
            product_category = ProductCategoryShortResponse(id=category.id, name=category.name, slug=category.slug)
        return FavoriteProductResponse(
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
            stock_display=build_stock_display(is_available=product.is_available, stock_quantity=product.stock_quantity),
            category=product_category,
            created_at=product.created_date,
        )
