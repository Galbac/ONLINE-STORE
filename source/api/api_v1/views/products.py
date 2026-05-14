from decimal import Decimal

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.repositories.category import CategoryRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.product import ProductListQueryParams, ProductListResponse, ProductSort, ProductType
from source.services.product import ProductService
from source.services.product_cache import ProductCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["products"])


@router.get(
    "/products",
    response_model=ProductListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Категория не найдена."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_products(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=settings.products.list_default_limit, ge=1, le=settings.products.list_max_limit),
    category_id: int | None = Query(default=None, ge=1),
    category_slug: str | None = Query(default=None, min_length=2, max_length=150),
    in_stock: bool | None = None,
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    has_discount: bool | None = None,
    product_type: ProductType | None = None,
    sort: ProductSort | None = None,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    product_service: FromDishka[ProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> ProductListResponse:
    try:
        return await product_service.get_products(
            session=session,
            redis_service=redis_service,
            product_cache_service=product_cache_service,
            product_repository=product_repository,
            category_repository=category_repository,
            query=ProductListQueryParams(
                page=page,
                limit=limit,
                category_id=category_id,
                category_slug=category_slug,
                in_stock=in_stock,
                min_price=min_price,
                max_price=max_price,
                has_discount=has_discount,
                product_type=product_type,
                sort=sort,
            ),
        )
    except CategoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from error
