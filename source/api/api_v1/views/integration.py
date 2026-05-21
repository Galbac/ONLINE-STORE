from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import verify_one_c_token
from source.common.commiter import Commiter
from source.config.settings import Settings
from source.repositories.category import CategoryRepository
from source.repositories.integration_log import IntegrationLogRepository
from source.repositories.product import ProductRepository
from source.schemas.pydantic.one_c import OneCCategoryImportRequest, OneCImportResultResponse, OneCProductImportRequest
from source.services.admin_product_cache import AdminProductCacheService
from source.services.admin_category_cache import AdminCategoryCacheService
from source.services.category_cache import CategoryCacheService
from source.services.one_c import CategorySyncService, IntegrationLogService, OneCImportService, ProductSyncService, SlugService
from source.services.product_cache import ProductCacheService
from source.services.redis import RedisService

router = APIRouter(tags=["integration"])


@router.post(
    "/integration/1c/categories",
    response_model=OneCImportResultResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def import_one_c_categories(
    body: OneCCategoryImportRequest,
    _token: None = Depends(verify_one_c_token),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    one_c_import_service: FromDishka[OneCImportService] = None,
    category_sync_service: FromDishka[CategorySyncService] = None,
    integration_log_service: FromDishka[IntegrationLogService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
) -> OneCImportResultResponse:
    if not body.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="items пустой")
    if len(body.items) > config.one_c.import_max_batch_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Превышен максимальный batch size")

    try:
        return await one_c_import_service.import_categories(
            session=session,
            redis_service=redis_service,
            data=body,
            commiter=commiter,
            category_repository=category_repository,
            integration_log_repository=integration_log_repository,
            category_sync_service=category_sync_service,
            integration_log_service=integration_log_service,
            category_cache_service=category_cache_service,
            admin_category_cache_service=admin_category_cache_service,
            product_cache_service=product_cache_service,
        )
    except Exception:
        await commiter.rollback()
        raise


@router.post(
    "/integration/1c/products",
    response_model=OneCImportResultResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def import_one_c_products(
    body: OneCProductImportRequest,
    _token: None = Depends(verify_one_c_token),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    one_c_import_service: FromDishka[OneCImportService] = None,
    product_sync_service: FromDishka[ProductSyncService] = None,
    slug_service: FromDishka[SlugService] = None,
    integration_log_service: FromDishka[IntegrationLogService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
) -> OneCImportResultResponse:
    if not body.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="items пустой")
    if len(body.items) > config.one_c.import_max_batch_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Превышен максимальный batch size")

    try:
        return await one_c_import_service.import_products(
            session=session,
            redis_service=redis_service,
            data=body,
            commiter=commiter,
            product_repository=product_repository,
            category_repository=category_repository,
            integration_log_repository=integration_log_repository,
            product_sync_service=product_sync_service,
            slug_service=slug_service,
            integration_log_service=integration_log_service,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
            category_cache_service=category_cache_service,
        )
    except Exception:
        await commiter.rollback()
        raise
