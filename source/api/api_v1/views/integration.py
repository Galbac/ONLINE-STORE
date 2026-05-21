from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import require_permission, verify_one_c_token
from source.common.commiter import Commiter
from source.config.settings import Settings
from source.repositories.category import CategoryRepository
from source.repositories.address import AddressRepository
from source.repositories.delivery_time_slot import DeliveryTimeSlotRepository
from source.repositories.integration_job import IntegrationJobRepository
from source.repositories.integration_log import IntegrationLogRepository
from source.repositories.order import OrderRepository
from source.repositories.order_item import OrderItemRepository
from source.repositories.payment import PaymentRepository
from source.repositories.pickup_point import PickupPointRepository
from source.repositories.product import ProductRepository
from source.repositories.product_image import ProductImageRepository
from source.repositories.product_price_history import ProductPriceHistoryRepository
from source.repositories.stock_movement import StockMovementRepository
from source.repositories.upload import UploadRepository
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError, OneCIntegrationDisabledError, OneCSyncAlreadyRunningError, OneCSyncError
from source.schemas.pydantic.one_c import AdminOneCSyncRequest, AdminOneCSyncResponse, OneCCategoryImportRequest, OneCImageImportRequest, OneCImportResultResponse, OneCMarkOrderSyncedRequest, OneCOrderSyncErrorRequest, OneCOrderSyncResponse, OneCOrderSyncStatus, OneCOrdersPendingQueryParams, OneCOrdersPendingResponse, OneCPriceImportRequest, OneCProductImportRequest, OneCStockImportRequest
from source.services.admin_order_cache import AdminOrderCacheService
from source.services.admin_dashboard_cache import AdminDashboardCacheService
from source.services.admin_product_cache import AdminProductCacheService
from source.services.admin_category_cache import AdminCategoryCacheService
from source.services.admin_auth import PermissionService
from source.services.cart_cache import CartCacheService
from source.services.category_cache import CategoryCacheService
from source.services.discount_cache import DiscountCacheService
from source.services.one_c import AdminOneCIntegrationService, CategorySyncService, ImageDownloadService, IntegrationJobService, IntegrationLogService, OneCClient, OneCImportService, OneCOrderPayloadBuilder, OneCOrderService, ProductImageSyncService, ProductPriceSyncService, ProductStockSyncService, ProductSyncService, SlugService
from source.services.order_cache import OrderCacheService
from source.services.product_cache import ProductCacheService
from source.services.redis import RedisLockService, RedisService
from source.services.storage import StorageService
from source.services.stock import StockMovementService

router = APIRouter(tags=["integration"])


@router.post(
    "/admin/integration/1c/sync/products",
    response_model=AdminOneCSyncResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def admin_sync_one_c_products(
    body: AdminOneCSyncRequest,
    current_user=Depends(require_permission("admin:integration_1c:sync")),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    admin_one_c_integration_service: FromDishka[AdminOneCIntegrationService] = None,
    one_c_client: FromDishka[OneCClient] = None,
    one_c_import_service: FromDishka[OneCImportService] = None,
    product_sync_service: FromDishka[ProductSyncService] = None,
    slug_service: FromDishka[SlugService] = None,
    integration_job_service: FromDishka[IntegrationJobService] = None,
    integration_log_service: FromDishka[IntegrationLogService] = None,
    redis_lock_service: FromDishka[RedisLockService] = None,
    permission_service: FromDishka[PermissionService] = None,
    integration_job_repository: FromDishka[IntegrationJobRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
) -> AdminOneCSyncResponse:
    try:
        return await admin_one_c_integration_service.sync_products(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=body,
            commiter=commiter,
            config=config,
            permission_service=permission_service,
            redis_lock_service=redis_lock_service,
            one_c_client=one_c_client,
            one_c_import_service=one_c_import_service,
            product_sync_service=product_sync_service,
            slug_service=slug_service,
            integration_job_service=integration_job_service,
            integration_log_service=integration_log_service,
            integration_job_repository=integration_job_repository,
            integration_log_repository=integration_log_repository,
            product_repository=product_repository,
            category_repository=category_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
            category_cache_service=category_cache_service,
        )
    except (AdminAuthAccessDeniedError, InactiveUserError) as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except OneCIntegrationDisabledError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Интеграция с 1С отключена") from error
    except OneCSyncAlreadyRunningError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Синхронизация товаров уже выполняется") from error
    except OneCSyncError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка подключения к 1С") from error


@router.post(
    "/admin/integration/1c/sync/prices",
    response_model=AdminOneCSyncResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def admin_sync_one_c_prices(
    body: AdminOneCSyncRequest,
    current_user=Depends(require_permission("admin:integration_1c:sync")),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    admin_one_c_integration_service: FromDishka[AdminOneCIntegrationService] = None,
    one_c_client: FromDishka[OneCClient] = None,
    one_c_import_service: FromDishka[OneCImportService] = None,
    product_price_sync_service: FromDishka[ProductPriceSyncService] = None,
    integration_job_service: FromDishka[IntegrationJobService] = None,
    integration_log_service: FromDishka[IntegrationLogService] = None,
    redis_lock_service: FromDishka[RedisLockService] = None,
    permission_service: FromDishka[PermissionService] = None,
    integration_job_repository: FromDishka[IntegrationJobRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_price_history_repository: FromDishka[ProductPriceHistoryRepository] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    discount_cache_service: FromDishka[DiscountCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
) -> AdminOneCSyncResponse:
    try:
        return await admin_one_c_integration_service.sync_prices(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=body,
            commiter=commiter,
            config=config,
            permission_service=permission_service,
            redis_lock_service=redis_lock_service,
            one_c_client=one_c_client,
            one_c_import_service=one_c_import_service,
            product_price_sync_service=product_price_sync_service,
            integration_job_service=integration_job_service,
            integration_log_service=integration_log_service,
            integration_job_repository=integration_job_repository,
            integration_log_repository=integration_log_repository,
            product_repository=product_repository,
            product_price_history_repository=product_price_history_repository,
            product_cache_service=product_cache_service,
            cart_cache_service=cart_cache_service,
            discount_cache_service=discount_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except (AdminAuthAccessDeniedError, InactiveUserError) as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except OneCIntegrationDisabledError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Интеграция с 1С отключена") from error
    except OneCSyncAlreadyRunningError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Синхронизация цен уже выполняется") from error
    except OneCSyncError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка подключения к 1С") from error


@router.post(
    "/admin/integration/1c/sync/stocks",
    response_model=AdminOneCSyncResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def admin_sync_one_c_stocks(
    body: AdminOneCSyncRequest,
    current_user=Depends(require_permission("admin:integration_1c:sync")),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    admin_one_c_integration_service: FromDishka[AdminOneCIntegrationService] = None,
    one_c_client: FromDishka[OneCClient] = None,
    one_c_import_service: FromDishka[OneCImportService] = None,
    product_stock_sync_service: FromDishka[ProductStockSyncService] = None,
    stock_movement_service: FromDishka[StockMovementService] = None,
    integration_job_service: FromDishka[IntegrationJobService] = None,
    integration_log_service: FromDishka[IntegrationLogService] = None,
    redis_lock_service: FromDishka[RedisLockService] = None,
    permission_service: FromDishka[PermissionService] = None,
    integration_job_repository: FromDishka[IntegrationJobRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    stock_movement_repository: FromDishka[StockMovementRepository] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    admin_dashboard_cache_service: FromDishka[AdminDashboardCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
) -> AdminOneCSyncResponse:
    try:
        return await admin_one_c_integration_service.sync_stocks(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=body,
            commiter=commiter,
            config=config,
            permission_service=permission_service,
            redis_lock_service=redis_lock_service,
            one_c_client=one_c_client,
            one_c_import_service=one_c_import_service,
            product_stock_sync_service=product_stock_sync_service,
            stock_movement_service=stock_movement_service,
            integration_job_service=integration_job_service,
            integration_log_service=integration_log_service,
            integration_job_repository=integration_job_repository,
            integration_log_repository=integration_log_repository,
            product_repository=product_repository,
            stock_movement_repository=stock_movement_repository,
            product_cache_service=product_cache_service,
            cart_cache_service=cart_cache_service,
            admin_dashboard_cache_service=admin_dashboard_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except (AdminAuthAccessDeniedError, InactiveUserError) as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except OneCIntegrationDisabledError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Интеграция с 1С отключена") from error
    except OneCSyncAlreadyRunningError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Синхронизация остатков уже выполняется") from error
    except OneCSyncError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка подключения к 1С") from error


@router.get(
    "/integration/1c/orders/pending",
    response_model=OneCOrdersPendingResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_one_c_pending_orders(
    _token: None = Depends(verify_one_c_token),
    limit: int | None = Query(default=None, ge=1),
    sync_status: OneCOrderSyncStatus | None = Query(default=None, alias="status"),
    session: FromDishka[AsyncSession] = None,
    config: FromDishka[Settings] = None,
    one_c_order_service: FromDishka[OneCOrderService] = None,
    order_payload_builder: FromDishka[OneCOrderPayloadBuilder] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
    delivery_time_slot_repository: FromDishka[DeliveryTimeSlotRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> OneCOrdersPendingResponse:
    effective_limit = limit if limit is not None else config.one_c.orders_pending_default_limit
    if effective_limit > config.one_c.orders_pending_max_limit:
        effective_limit = config.one_c.orders_pending_max_limit

    return await one_c_order_service.get_pending_orders(
        session=session,
        query=OneCOrdersPendingQueryParams(limit=effective_limit, status=sync_status),
        order_repository=order_repository,
        order_item_repository=order_item_repository,
        payment_repository=payment_repository,
        address_repository=address_repository,
        pickup_point_repository=pickup_point_repository,
        delivery_time_slot_repository=delivery_time_slot_repository,
        product_repository=product_repository,
        order_payload_builder=order_payload_builder,
    )


@router.post(
    "/integration/1c/orders/{order_id}/mark-synced",
    response_model=OneCOrderSyncResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def mark_one_c_order_synced(
    order_id: int,
    body: OneCMarkOrderSyncedRequest,
    _token: None = Depends(verify_one_c_token),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    one_c_order_service: FromDishka[OneCOrderService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
) -> OneCOrderSyncResponse:
    if order_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный order_id")
    if config.one_c.external_order_id_required and body.external_1c_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="external_1c_id обязателен")

    try:
        response = await one_c_order_service.mark_order_synced(
            session=session,
            redis_service=redis_service,
            order_id=order_id,
            data=body,
            commiter=commiter,
            order_repository=order_repository,
            integration_log_repository=integration_log_repository,
            order_cache_service=order_cache_service,
        )
    except Exception:
        await commiter.rollback()
        raise

    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    return response


@router.post(
    "/integration/1c/orders/{order_id}/sync-error",
    response_model=OneCOrderSyncResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def mark_one_c_order_sync_error(
    order_id: int,
    body: OneCOrderSyncErrorRequest,
    _token: None = Depends(verify_one_c_token),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    one_c_order_service: FromDishka[OneCOrderService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    admin_order_cache_service: FromDishka[AdminOrderCacheService] = None,
) -> OneCOrderSyncResponse:
    if order_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный order_id")

    try:
        response = await one_c_order_service.mark_order_sync_error(
            session=session,
            redis_service=redis_service,
            order_id=order_id,
            data=body,
            commiter=commiter,
            order_repository=order_repository,
            integration_log_repository=integration_log_repository,
            order_cache_service=order_cache_service,
            admin_order_cache_service=admin_order_cache_service,
        )
    except Exception:
        await commiter.rollback()
        raise

    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    return response


@router.post(
    "/integration/1c/categories",
    response_model=OneCImportResultResponse,
    response_model_exclude_none=True,
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
    response_model_exclude_none=True,
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


@router.post(
    "/integration/1c/prices",
    response_model=OneCImportResultResponse,
    response_model_exclude={"created"},
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def import_one_c_prices(
    body: OneCPriceImportRequest,
    _token: None = Depends(verify_one_c_token),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    one_c_import_service: FromDishka[OneCImportService] = None,
    product_price_sync_service: FromDishka[ProductPriceSyncService] = None,
    integration_log_service: FromDishka[IntegrationLogService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_price_history_repository: FromDishka[ProductPriceHistoryRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
) -> OneCImportResultResponse:
    if not body.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="items пустой")
    if len(body.items) > config.one_c.import_max_batch_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Превышен максимальный batch size")

    try:
        return await one_c_import_service.import_prices(
            session=session,
            redis_service=redis_service,
            data=body,
            commiter=commiter,
            product_repository=product_repository,
            product_price_history_repository=product_price_history_repository,
            integration_log_repository=integration_log_repository,
            product_price_sync_service=product_price_sync_service,
            integration_log_service=integration_log_service,
            product_cache_service=product_cache_service,
            cart_cache_service=cart_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except Exception:
        await commiter.rollback()
        raise


@router.post(
    "/integration/1c/stocks",
    response_model=OneCImportResultResponse,
    response_model_exclude={"created"},
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def import_one_c_stocks(
    body: OneCStockImportRequest,
    _token: None = Depends(verify_one_c_token),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    one_c_import_service: FromDishka[OneCImportService] = None,
    product_stock_sync_service: FromDishka[ProductStockSyncService] = None,
    stock_movement_service: FromDishka[StockMovementService] = None,
    integration_log_service: FromDishka[IntegrationLogService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    stock_movement_repository: FromDishka[StockMovementRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    admin_dashboard_cache_service: FromDishka[AdminDashboardCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
) -> OneCImportResultResponse:
    if not body.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="items пустой")
    if len(body.items) > config.one_c.import_max_batch_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Превышен максимальный batch size")

    try:
        return await one_c_import_service.import_stocks(
            session=session,
            redis_service=redis_service,
            data=body,
            commiter=commiter,
            product_repository=product_repository,
            stock_movement_repository=stock_movement_repository,
            integration_log_repository=integration_log_repository,
            product_stock_sync_service=product_stock_sync_service,
            stock_movement_service=stock_movement_service,
            integration_log_service=integration_log_service,
            product_cache_service=product_cache_service,
            cart_cache_service=cart_cache_service,
            admin_dashboard_cache_service=admin_dashboard_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except Exception:
        await commiter.rollback()
        raise


@router.post(
    "/integration/1c/images",
    response_model=OneCImportResultResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def import_one_c_images(
    body: OneCImageImportRequest,
    _token: None = Depends(verify_one_c_token),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    one_c_import_service: FromDishka[OneCImportService] = None,
    product_image_sync_service: FromDishka[ProductImageSyncService] = None,
    image_download_service: FromDishka[ImageDownloadService] = None,
    storage_service: FromDishka[StorageService] = None,
    integration_log_service: FromDishka[IntegrationLogService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_image_repository: FromDishka[ProductImageRepository] = None,
    upload_repository: FromDishka[UploadRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
) -> OneCImportResultResponse:
    if not config.one_c.import_images_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Импорт изображений из 1С отключён")
    if not body.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="items пустой")
    if len(body.items) > config.one_c.import_max_batch_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Превышен максимальный batch size")

    try:
        return await one_c_import_service.import_images(
            session=session,
            redis_service=redis_service,
            data=body,
            commiter=commiter,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            upload_repository=upload_repository,
            integration_log_repository=integration_log_repository,
            product_image_sync_service=product_image_sync_service,
            image_download_service=image_download_service,
            storage_service=storage_service,
            integration_log_service=integration_log_service,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except Exception:
        await commiter.rollback()
        raise
