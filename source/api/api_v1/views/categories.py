from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.category import CategoryNotFoundError
from source.repositories.category import CategoryRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.category import (
    CategoryDetailQueryParams,
    CategoryDetailResponse,
    CategoryListQueryParams,
    CategoryListResponse,
    CategoryTreeQueryParams,
    CategoryTreeResponse,
)
from source.services.category import CategoryService
from source.services.category_cache import CategoryCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["categories"])


@router.get(
    "/categories/tree",
    response_model=CategoryTreeResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные query params."},
        status.HTTP_404_NOT_FOUND: {"description": "root_id не найден или категория неактивна."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_category_tree(
    include_empty: bool = False,
    max_depth: int = Query(default=settings.categories.tree_max_depth_default, ge=1, le=10),
    root_id: int | None = Query(default=None, ge=1),
    with_products_count: bool = True,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    category_service: FromDishka[CategoryService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> CategoryTreeResponse:
    try:
        return await category_service.get_category_tree(
            session=session,
            redis_service=redis_service,
            category_cache_service=category_cache_service,
            category_repository=category_repository,
            query=CategoryTreeQueryParams(
                include_empty=include_empty,
                max_depth=max_depth,
                root_id=root_id,
                with_products_count=with_products_count,
            ),
        )
    except CategoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from error


@router.get(
    "/categories/{category_id}",
    response_model=CategoryDetailResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверный category_id или query params."},
        status.HTTP_404_NOT_FOUND: {"description": "Категория не найдена."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_category_by_id(
    category_id: int = Path(ge=1),
    with_children: bool = True,
    with_breadcrumbs: bool = True,
    with_products_count: bool = True,
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    category_service: FromDishka[CategoryService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> CategoryDetailResponse:
    try:
        return await category_service.get_category_by_id(
            session=session,
            redis_service=redis_service,
            category_cache_service=category_cache_service,
            category_repository=category_repository,
            product_repository=product_repository,
            category_id=category_id,
            query=CategoryDetailQueryParams(
                with_children=with_children,
                with_breadcrumbs=with_breadcrumbs,
                with_products_count=with_products_count,
            ),
        )
    except CategoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        ) from error


@router.get(
    "/categories",
    response_model=CategoryListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные query params."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_categories(
    parent_id: int | None = Query(default=None, ge=1),
    only_root: bool = False,
    include_empty: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    category_service: FromDishka[CategoryService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> CategoryListResponse:
    return await category_service.get_categories(
        session=session,
        redis_service=redis_service,
        category_cache_service=category_cache_service,
        category_repository=category_repository,
        query=CategoryListQueryParams(
            parent_id=parent_id,
            only_root=only_root,
            include_empty=include_empty,
            limit=limit,
            offset=offset,
        ),
    )
