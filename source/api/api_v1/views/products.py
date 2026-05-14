from decimal import Decimal

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.errors.product import ProductNotFoundError
from source.repositories.category import CategoryRepository
from source.repositories.product import ProductRepository
from source.repositories.product_image import ProductImageRepository
from source.schemas.pydantic.product import (
    ProductDetailQueryParams,
    ProductDetailResponse,
    ProductDiscountedQueryParams,
    ProductDiscountedResponse,
    ProductDiscountedSort,
    ProductListQueryParams,
    ProductListResponse,
    ProductPopularQueryParams,
    ProductPopularResponse,
    ProductSearchQueryParams,
    ProductSearchResponse,
    ProductSearchSort,
    ProductSort,
    ProductType,
)
from source.services.product import ProductService
from source.services.product_cache import ProductCacheService
from source.services.redis import RedisService
from source.utils.search import normalize_search_query
from source.utils.slug import normalize_slug, validate_slug

router = APIRouter(tags=["products"])


@router.get(
    "/products/discounted",
    response_model=ProductDiscountedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Категория не найдена."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_discounted_products(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=settings.products.list_default_limit, ge=1, le=settings.products.list_max_limit),
    category_id: int | None = Query(default=None, ge=1),
    in_stock: bool = True,
    sort: ProductDiscountedSort = "discount_desc",
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    product_service: FromDishka[ProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> ProductDiscountedResponse:
    try:
        return await product_service.get_discounted_products(
            session=session,
            redis_service=redis_service,
            product_cache_service=product_cache_service,
            product_repository=product_repository,
            category_repository=category_repository,
            query=ProductDiscountedQueryParams(
                page=page,
                limit=limit,
                category_id=category_id,
                in_stock=in_stock,
                sort=sort,
            ),
        )
    except CategoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from error


@router.get(
    "/products/popular",
    response_model=ProductPopularResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Категория не найдена."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_popular_products(
    limit: int = Query(default=settings.products.popular_default_limit, ge=1, le=settings.products.list_max_limit),
    category_id: int | None = Query(default=None, ge=1),
    period_days: int = Query(default=30, ge=1),
    in_stock: bool = True,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    product_service: FromDishka[ProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> ProductPopularResponse:
    try:
        return await product_service.get_popular_products(
            session=session,
            redis_service=redis_service,
            product_cache_service=product_cache_service,
            product_repository=product_repository,
            category_repository=category_repository,
            query=ProductPopularQueryParams(
                limit=limit,
                category_id=category_id,
                period_days=period_days,
                in_stock=in_stock,
            ),
        )
    except CategoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from error


@router.get(
    "/products/search",
    response_model=ProductSearchResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверный поисковый запрос или query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Категория не найдена."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def search_products(
    q: str | None = Query(
        default=None,
        max_length=settings.products.search_max_query_length,
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=settings.products.list_default_limit, ge=1, le=settings.products.list_max_limit),
    category_id: int | None = Query(default=None, ge=1),
    in_stock: bool | None = None,
    has_discount: bool | None = None,
    sort: ProductSearchSort = "relevance",
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    product_service: FromDishka[ProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> ProductSearchResponse:
    normalized_query = _normalize_required_search_query(q)

    try:
        return await product_service.search_products(
            session=session,
            redis_service=redis_service,
            product_cache_service=product_cache_service,
            product_repository=product_repository,
            category_repository=category_repository,
            query=ProductSearchQueryParams(
                q=normalized_query,
                page=page,
                limit=limit,
                category_id=category_id,
                in_stock=in_stock,
                has_discount=has_discount,
                sort=sort,
            ),
        )
    except CategoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from error


def _normalize_required_search_query(query: str | None) -> str:
    if query is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поисковый запрос обязателен",
        )

    normalized_query = normalize_search_query(query)
    if not normalized_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поисковый запрос обязателен",
        )
    if len(normalized_query) < settings.products.search_min_query_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поисковый запрос слишком короткий",
        )
    return normalized_query


@router.get(
    "/products/slug/{slug}",
    response_model=ProductDetailResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверный slug или query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Товар не найден."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_product_by_slug(
    slug: str = Path(min_length=2, max_length=200),
    with_similar: bool = False,
    with_breadcrumbs: bool = True,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    product_service: FromDishka[ProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_image_repository: FromDishka[ProductImageRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> ProductDetailResponse:
    normalized_slug = normalize_slug(slug)
    if not validate_slug(normalized_slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный slug",
        )

    try:
        return await product_service.get_product_by_slug(
            session=session,
            redis_service=redis_service,
            product_cache_service=product_cache_service,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            category_repository=category_repository,
            slug=normalized_slug,
            query=ProductDetailQueryParams(
                with_similar=with_similar,
                with_breadcrumbs=with_breadcrumbs,
            ),
        )
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        ) from error


@router.get(
    "/products/{product_id}",
    response_model=ProductDetailResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверный product_id или query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Товар не найден."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_product_by_id(
    product_id: int = Path(ge=1),
    with_similar: bool = False,
    with_breadcrumbs: bool = True,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    product_service: FromDishka[ProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_image_repository: FromDishka[ProductImageRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> ProductDetailResponse:
    try:
        return await product_service.get_product_by_id(
            session=session,
            redis_service=redis_service,
            product_cache_service=product_cache_service,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            category_repository=category_repository,
            product_id=product_id,
            query=ProductDetailQueryParams(
                with_similar=with_similar,
                with_breadcrumbs=with_breadcrumbs,
            ),
        )
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        ) from error


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
