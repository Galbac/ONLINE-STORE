from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.repositories.category import CategoryRepository
from source.schemas.pydantic.category import CategoryListQueryParams, CategoryListResponse
from source.services.category import CategoryService
from source.services.category_cache import CategoryCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["categories"])


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
