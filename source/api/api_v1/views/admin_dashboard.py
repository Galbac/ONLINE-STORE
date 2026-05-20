from dishka.integrations.fastapi import FromDishka, inject
from datetime import date

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, verify_access_token
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.category import CategoryNotFoundError
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError, InvalidCredentialsError
from source.errors.product import (
    ProductActiveOrderExistsError,
    ProductBarcodeAlreadyExistsError,
    ProductImageNotFoundError,
    ProductImageOwnershipError,
    ProductNotFoundError,
    ProductSkuAlreadyExistsError,
    ProductSlugAlreadyExistsError,
)
from source.errors.upload import UploadFileMissingError, UploadFileTooLargeError, UploadStorageError, UploadUnsupportedFormatError
from source.repositories.admin_audit_log import AdminAuditLogRepository
from source.repositories.category import CategoryRepository
from source.repositories.discount import DiscountRepository
from source.repositories.order import OrderRepository
from source.repositories.order_item import OrderItemRepository
from source.repositories.product import ProductRepository
from source.repositories.product_availability_log import ProductAvailabilityLogRepository
from source.repositories.product_image import ProductImageRepository
from source.repositories.stock_movement import StockMovementRepository
from source.repositories.upload import UploadRepository
from source.repositories.user import UserRepository
from source.config.settings import Settings
from source.schemas.pydantic.admin_dashboard import (
    AdminDashboardResponse,
    AdminLowStockQueryParams,
    AdminLowStockResponse,
    AdminSalesQueryParams,
    AdminSalesResponse,
)
from source.schemas.pydantic.admin_category import (
    AdminCategoryListQueryParams,
    AdminCategoryListResponse,
)
from source.schemas.pydantic.admin_product import (
    AdminProductCreateRequest,
    AdminProductDetailResponse,
    AdminProductImageResponse,
    AdminProductImagesSortResponse,
    AdminProductListQueryParams,
    AdminProductListResponse,
    AdminProductUpdateRequest,
    AdminProductUpdateResponse,
    MessageResponse,
    ProductAvailabilityResponse,
    ProductAvailabilityUpdateRequest,
    ProductImagesSortRequest,
    ProductStockResponse,
    ProductStockUpdateRequest,
)
from source.services.category_cache import CategoryCacheService
from source.services.admin_auth import PermissionService
from source.services.admin_category import AdminCategoryService
from source.services.admin_category_cache import AdminCategoryCacheService
from source.services.admin_dashboard import AdminDashboardService
from source.services.admin_dashboard_cache import AdminDashboardCacheService
from source.services.admin_product import AdminProductService
from source.services.admin_product_cache import AdminProductCacheService
from source.services.admin_product_image import AdminProductImageService
from source.services.product_cache import ProductCacheService
from source.services.redis import RedisService
from source.services.storage import StorageService
from source.services.stock import StockMovementService, StockService
from source.services.upload import UploadService

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


@router.get("/categories", response_model=AdminCategoryListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_categories(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    page: str = Query(default="1"),
    limit: str = Query(default="50"),
    q: str | None = Query(default=None),
    parent_id: str | None = Query(default=None),
    is_active: str | None = Query(default=None),
    include_deleted: str = Query(default="false"),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_category_service: FromDishka[AdminCategoryService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> AdminCategoryListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminCategoryListQueryParams(
            page=page,
            limit=limit,
            q=q,
            parent_id=parent_id,
            is_active=is_active,
            include_deleted=include_deleted,
        )
        return await admin_category_service.get_categories(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            category_repository=category_repository,
            product_repository=product_repository,
            admin_category_cache_service=admin_category_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные параметры запроса") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.get("/products", response_model=AdminProductListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_products(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    page: str = Query(default="1"),
    limit: str = Query(default="50"),
    q: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    is_active: str | None = Query(default=None),
    is_available: str | None = Query(default=None),
    in_stock: str | None = Query(default=None),
    low_stock: str | None = Query(default=None),
    product_type: str | None = Query(default=None),
    sync_status: str | None = Query(default=None),
    sort: str = Query(default="newest"),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_product_service: FromDishka[AdminProductService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> AdminProductListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminProductListQueryParams(
            page=page,
            limit=limit,
            q=q,
            category_id=category_id,
            is_active=is_active,
            is_available=is_available,
            in_stock=in_stock,
            low_stock=low_stock,
            product_type=product_type,
            sync_status=sync_status,
            sort=sort,
        )
        return await admin_product_service.get_products(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            product_repository=product_repository,
            admin_product_cache_service=admin_product_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные параметры запроса") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.get("/products/{product_id}", response_model=AdminProductDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_product_detail(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    product_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_product_service: FromDishka[AdminProductService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_image_repository: FromDishka[ProductImageRepository] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
) -> AdminProductDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_service.get_product_detail(
            session=session,
            redis_service=redis_service,
            user=current_user,
            product_id=product_id,
            permission_service=permission_service,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            discount_repository=discount_repository,
            admin_product_cache_service=admin_product_cache_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except ProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error


@router.post("/products/{product_id}/images", response_model=AdminProductImageResponse, status_code=status.HTTP_201_CREATED)
@inject
async def add_admin_product_image(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    product_id: int = Path(ge=1),
    file: UploadFile | None = File(default=None),
    sort_order: int = Form(default=0),
    is_main: bool = Form(default=False),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    admin_product_image_service: FromDishka[AdminProductImageService] = None,
    storage_service: FromDishka[StorageService] = None,
    upload_service: FromDishka[UploadService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    upload_repository: FromDishka[UploadRepository] = None,
    product_image_repository: FromDishka[ProductImageRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminProductImageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_image_service.add_image(
            session=session,
            redis_service=redis_service,
            user=current_user,
            product_id=product_id,
            file=file,
            sort_order=sort_order,
            is_main=is_main,
            commiter=commiter,
            media_settings=config.media,
            permission_service=permission_service,
            product_repository=product_repository,
            upload_service=upload_service,
            storage_service=storage_service,
            upload_repository=upload_repository,
            product_image_repository=product_image_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except UploadFileMissingError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не передан") from error
    except UploadUnsupportedFormatError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неподдерживаемый формат файла") from error
    except UploadFileTooLargeError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой") from error
    except UploadStorageError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка загрузки файла") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except ProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error


@router.delete("/products/{product_id}/images/{image_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@inject
async def delete_admin_product_image(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    product_id: int = Path(ge=1),
    image_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_product_image_service: FromDishka[AdminProductImageService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_image_repository: FromDishka[ProductImageRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> MessageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_image_service.delete_image(
            session=session,
            redis_service=redis_service,
            user=current_user,
            product_id=product_id,
            image_id=image_id,
            commiter=commiter,
            permission_service=permission_service,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except ProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except ProductImageNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено") from error
    except ProductImageOwnershipError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Изображение не принадлежит товару") from error


@router.patch("/products/{product_id}/images/sort", response_model=AdminProductImagesSortResponse, status_code=status.HTTP_200_OK)
@inject
async def sort_admin_product_images(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    product_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_product_image_service: FromDishka[AdminProductImageService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_image_repository: FromDishka[ProductImageRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminProductImagesSortResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_image_service.sort_images(
            session=session,
            redis_service=redis_service,
            user=current_user,
            product_id=product_id,
            data=ProductImagesSortRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            product_repository=product_repository,
            product_image_repository=product_image_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except ValidationError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except ProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except ProductImageNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено") from error
    except ProductImageOwnershipError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Изображение не принадлежит товару") from error


@router.patch("/products/{product_id}/stock", response_model=ProductStockResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_product_stock(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    product_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_product_service: FromDishka[AdminProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    stock_service: FromDishka[StockService] = None,
    stock_movement_service: FromDishka[StockMovementService] = None,
    stock_movement_repository: FromDishka[StockMovementRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> ProductStockResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_service.update_stock(
            session=session,
            redis_service=redis_service,
            user=current_user,
            product_id=product_id,
            data=ProductStockUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            product_repository=product_repository,
            stock_service=stock_service,
            stock_movement_service=stock_movement_service,
            stock_movement_repository=stock_movement_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except ValueError as error:
        detail = "Остаток не может быть отрицательным" if "negative" in str(error) else "Неверная операция"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except ProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error


@router.post("/products", response_model=AdminProductDetailResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_admin_product(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_product_service: FromDishka[AdminProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminProductDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_service.create_product(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminProductCreateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            product_repository=product_repository,
            category_repository=category_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
            admin_category_cache_service=admin_category_cache_service,
            category_cache_service=category_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except CategoryNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error
    except ProductSlugAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug уже занят") from error
    except ProductSkuAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU уже занят") from error
    except ProductBarcodeAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Barcode уже занят") from error


@router.delete("/products/{product_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@inject
async def delete_admin_product(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    product_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_product_service: FromDishka[AdminProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> MessageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_service.delete_product(
            session=session,
            redis_service=redis_service,
            user=current_user,
            product_id=product_id,
            commiter=commiter,
            permission_service=permission_service,
            product_repository=product_repository,
            order_item_repository=order_item_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
            admin_category_cache_service=admin_category_cache_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except ProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except ProductActiveOrderExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Товар используется в активных заказах") from error


@router.patch("/products/{product_id}/availability", response_model=ProductAvailabilityResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_product_availability(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    product_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_product_service: FromDishka[AdminProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    product_availability_log_repository: FromDishka[ProductAvailabilityLogRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> ProductAvailabilityResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_service.update_availability(
            session=session,
            redis_service=redis_service,
            user=current_user,
            product_id=product_id,
            data=ProductAvailabilityUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            product_repository=product_repository,
            product_availability_log_repository=product_availability_log_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except ProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error


@router.patch("/products/{product_id}", response_model=AdminProductUpdateResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_product(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    product_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_product_service: FromDishka[AdminProductService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    admin_product_cache_service: FromDishka[AdminProductCacheService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminProductUpdateResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_product_service.update_product(
            session=session,
            redis_service=redis_service,
            user=current_user,
            product_id=product_id,
            data=AdminProductUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            product_repository=product_repository,
            category_repository=category_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            product_cache_service=product_cache_service,
            admin_product_cache_service=admin_product_cache_service,
            admin_category_cache_service=admin_category_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except ValueError as error:
        detail = "Нет полей для обновления" if str(error) == "No fields to update" else "Неверные данные"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except ProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except CategoryNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error
    except ProductSlugAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug уже занят") from error
    except ProductSkuAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU уже занят") from error
    except ProductBarcodeAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Barcode уже занят") from error


@router.get("/dashboard", response_model=AdminDashboardResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_dashboard(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_dashboard_service: FromDishka[AdminDashboardService] = None,
    admin_dashboard_cache_service: FromDishka[AdminDashboardCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    user_repository: FromDishka[UserRepository] = None,
) -> AdminDashboardResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_dashboard_service.get_summary(
            session=session,
            redis_service=redis_service,
            user=current_user,
            permission_service=permission_service,
            order_repository=order_repository,
            product_repository=product_repository,
            user_repository=user_repository,
            admin_dashboard_cache_service=admin_dashboard_cache_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.get("/dashboard/low-stock", response_model=AdminLowStockResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_dashboard_low_stock(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category_id: int | None = Query(default=None, ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_dashboard_service: FromDishka[AdminDashboardService] = None,
    admin_dashboard_cache_service: FromDishka[AdminDashboardCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> AdminLowStockResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminLowStockQueryParams(
            limit=limit,
            offset=offset,
            category_id=category_id,
        )
        return await admin_dashboard_service.get_low_stock_products(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            product_repository=product_repository,
            admin_dashboard_cache_service=admin_dashboard_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные параметры запроса") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.get("/dashboard/sales", response_model=AdminSalesResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_dashboard_sales(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    date_from: date | None = None,
    date_to: date | None = None,
    group_by: str = Query(default="day", pattern="^(day|week|month)$"),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_dashboard_service: FromDishka[AdminDashboardService] = None,
    admin_dashboard_cache_service: FromDishka[AdminDashboardCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> AdminSalesResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminSalesQueryParams(
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
        )
        return await admin_dashboard_service.get_sales(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            order_repository=order_repository,
            admin_dashboard_cache_service=admin_dashboard_cache_service,
        )
    except (ValueError, ValidationError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные даты") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    AdminProductImagesSortResponse,
