from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.repositories.discount import DiscountRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.discount import ActiveDiscountsQueryParams, ActiveDiscountsResponse, DiscountProductsQueryParams, DiscountProductsResponse
from source.services.discount import DiscountService
from source.services.discount_cache import DiscountCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["discounts"])


@router.get("/discounts/active", response_model=ActiveDiscountsResponse, status_code=status.HTTP_200_OK)
@inject
async def get_active_discounts(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    type: str | None = Query(default=None, pattern="^(product|category|cart)$"),
    only_with_products: bool = True,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    discount_service: FromDishka[DiscountService] = None,
    discount_cache_service: FromDishka[DiscountCacheService] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
) -> ActiveDiscountsResponse:
    try:
        query = ActiveDiscountsQueryParams(limit=limit, offset=offset, type=type, only_with_products=only_with_products)
        return await discount_service.get_active_discounts(
            session=session,
            redis_service=redis_service,
            discount_cache_service=discount_cache_service,
            discount_repository=discount_repository,
            query=query,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get("/discounts/products", response_model=DiscountProductsResponse, response_model_exclude_none=True, status_code=status.HTTP_200_OK)
@inject
async def get_discount_products(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=100),
    category_id: int | None = Query(default=None, ge=1),
    in_stock: bool = True,
    sort: str = Query(default="discount_desc", pattern="^(discount_desc|price_asc|price_desc|newest)$"),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    discount_service: FromDishka[DiscountService] = None,
    discount_cache_service: FromDishka[DiscountCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> DiscountProductsResponse:
    try:
        query = DiscountProductsQueryParams(page=page, limit=limit, category_id=category_id, in_stock=in_stock, sort=sort)
        return await discount_service.get_discounted_products(
            session=session,
            redis_service=redis_service,
            discount_cache_service=discount_cache_service,
            product_repository=product_repository,
            query=query,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error
