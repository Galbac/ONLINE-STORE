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
from source.repositories.stock_alert import StockAlertRepository
from source.common.commiter import Commiter
from source.schemas.pydantic.recommendation import ProductRecommendationResponse
from source.schemas.pydantic.stock_alert import StockAlertSubscribeRequest, StockAlertSubscribeResponse
from source.schemas.pydantic.product import (
    ProductDetailQueryParams,
    ProductDetailResponse,
    ProductDiscountedQueryParams,
    ProductDiscountedResponse,
    ProductDiscountedSort,
    ProductListQueryParams,
    ProductListResponse,
    ProductNewQueryParams,
    ProductNewResponse,
    ProductPopularQueryParams,
    ProductPopularResponse,
    ProductSearchQueryParams,
    ProductSearchResponse,
    ProductSearchSort,
    ProductSimilarQueryParams,
    ProductSimilarResponse,
    ProductSort,
    ProductType,
)
from source.schemas.pydantic.search_suggestions import (
    SearchSuggestionsResponse,
    SuggestionCategoryItem,
    SuggestionProductItem,
)
from source.services.product import ProductService
from source.services.product_cache import ProductCacheService
from source.services.redis import RedisService
from source.utils.search import normalize_search_query
from source.utils.slug import normalize_slug, validate_slug

router = APIRouter(tags=["products"])


@router.get(
    "/products/new",
    response_model=ProductNewResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Категория не найдена."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_new_products(
    limit: int = Query(default=settings.products.new_default_limit, ge=1, le=settings.products.list_max_limit),
    category_id: int | None = Query(default=None, ge=1),
    in_stock: bool = True,
    days: int = Query(default=settings.products.new_default_days, ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    product_service: FromDishka[ProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> ProductNewResponse:
    try:
        return await product_service.get_new_products(
            session=session,
            redis_service=redis_service,
            product_cache_service=product_cache_service,
            product_repository=product_repository,
            category_repository=category_repository,
            query=ProductNewQueryParams(
                limit=limit,
                category_id=category_id,
                in_stock=in_stock,
                days=days,
            ),
        )
    except CategoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from error


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
    "/products/search/suggestions",
    response_model=SearchSuggestionsResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_search_suggestions(
    q: str = Query(default="", max_length=100),
    session: FromDishka[AsyncSession] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> SearchSuggestionsResponse:
    query_str = q.strip()
    if len(query_str) < 2:
        return SearchSuggestionsResponse(query=query_str, categories=[], products=[])

    matching_categories = await category_repository.search_by_name(
        session=session,
        query=query_str,
        limit=4,
    )

    search_params = ProductSearchQueryParams(q=query_str, limit=6, page=1)
    matching_products = await product_repository.search_active(
        session=session,
        query=search_params,
    )

    return SearchSuggestionsResponse(
        query=query_str,
        categories=[
            SuggestionCategoryItem(id=c.id, name=c.name, slug=c.slug)
            for c in matching_categories
        ],
        products=[
            SuggestionProductItem(
                id=p.id,
                name=p.name,
                slug=p.slug,
                price=p.price,
                preview_image_url=p.preview_image_url,
            )
            for p in matching_products
        ],
    )


@router.get(
    "/products/search/popular",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
)
async def get_popular_searches() -> list[str]:
    return [
        "Фрукты и ягоды",
        "Молоко фермерское",
        "Сыр твердый",
        "Свежий хлеб",
        "Мясо и птица",
        "Кофе зерновой",
        "Авокадо Хасс",
        "Без сахара",
    ]


@router.get(
    "/products/{product_id}/similar",
    response_model=ProductSimilarResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверный product_id или query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Исходный товар не найден."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_similar_products(
    product_id: int = Path(ge=1),
    limit: int = Query(default=settings.products.similar_default_limit, ge=1, le=50),
    in_stock: bool = True,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    product_service: FromDishka[ProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> ProductSimilarResponse:
    try:
        return await product_service.get_similar_products(
            session=session,
            redis_service=redis_service,
            product_cache_service=product_cache_service,
            product_repository=product_repository,
            product_id=product_id,
            query=ProductSimilarQueryParams(
                limit=limit,
                in_stock=in_stock,
            ),
        )
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Исходный товар не найден",
        ) from error


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


@router.post(
    "/products/{product_id}/subscribe-stock",
    response_model=StockAlertSubscribeResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def subscribe_to_stock_alert(
    product_id: int,
    body: StockAlertSubscribeRequest,
    session: FromDishka[AsyncSession] = None,
    product_repository: FromDishka[ProductRepository] = None,
    stock_alert_repository: FromDishka[StockAlertRepository] = None,
    commiter: FromDishka[Commiter] = None,
) -> StockAlertSubscribeResponse:
    product = await product_repository.get_by_id(session=session, product_id=product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")

    await stock_alert_repository.create_alert(
        session=session,
        product_id=product_id,
        email=body.email,
        phone=body.phone,
    )
    await commiter.commit()
    return StockAlertSubscribeResponse(
        message="Вы успешно подписались на уведомление о поступлении товара",
        product_id=product_id,
    )


@router.get(
    "/products/{product_id}/recommendations",
    response_model=ProductRecommendationResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_product_recommendations(
    product_id: int,
    limit: int = Query(default=4, ge=1, le=12),
    session: FromDishka[AsyncSession] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> ProductRecommendationResponse:
    product = await product_repository.get_by_id(session=session, product_id=product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")

    limit_count = limit.default if hasattr(limit, "default") else limit
    similar_params = ProductSimilarQueryParams(limit=int(limit_count))
    items = await product_repository.get_similar_active(
        session=session,
        product_id=product_id,
        category_id=product.category_id,
        query=similar_params,
    )
    return ProductRecommendationResponse(
        product_id=product_id,
        items=items,
    )
