from dishka.integrations.fastapi import FromDishka, inject
from datetime import date

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Path, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, require_permission, verify_access_token
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.category import CategoryCycleError, CategoryNotFoundError, CategorySlugAlreadyExistsError
from source.errors.category import CategoryHasActiveChildrenError, CategoryHasActiveProductsError
from source.errors.delivery import (
    DeliveryZoneActiveOrdersError,
    DeliveryZoneAlreadyExistsError,
    DeliveryZoneNotFoundError,
    EmptyDeliverySettingsUpdateError,
    EmptyDeliveryZoneUpdateError,
    EmptyPickupPointUpdateError,
    PickupPointAlreadyExistsError,
    PickupPointAdminNotFoundError,
)
from source.errors.discount import DiscountConflictError, DiscountExpiredError, DiscountNotFoundError, EmptyDiscountUpdateError
from source.errors.auth import (
    AdminAuthAccessDeniedError,
    AdminRoleNotFoundError,
    AdminStaffSelfDeleteError,
    AdminStaffSelfRoleChangeError,
    AdminStaffInvalidRoleError,
    AdminStaffNotFoundError,
    EmptyAdminStaffUpdateError,
    AdminUserAlreadyBlockedError,
    AdminUserNotFoundError,
    AdminUserNotBlockedError,
    EmptyUserProfileUpdateError,
    EmptyOrderUpdateError,
    InactiveUserError,
    InvalidCredentialsError,
    LastActiveAdminDeleteError,
    LastActiveAdminDeactivationError,
    LastActiveAdminRoleChangeError,
    OneCIntegrationDisabledError,
    OneCSyncError,
    OrderAlreadyCancelledError,
    OrderAlreadySyncedError,
    OrderCompletedCancellationError,
    OrderConfirmNotAllowedError,
    OrderFieldNotEditableError,
    OrderInvalidStatusError,
    OrderItemsNotFoundError,
    OrderNotFoundError,
    OrderPrintFormatError,
    OrderStatusTransitionError,
    OrderUpdateNotAllowedError,
    OrderUnavailableItemsError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.errors.product import (
    ProductActiveOrderExistsError,
    ProductBarcodeAlreadyExistsError,
    ProductImageNotFoundError,
    ProductImageOwnershipError,
    ProductNotFoundError,
    ProductSkuAlreadyExistsError,
    ProductSlugAlreadyExistsError,
)
from source.errors.promo_code import (
    EmptyPromoCodeUpdateError,
    PromoCodeAlreadyExistsError,
    PromoCodeNotFoundError,
    PromoCodeUsageLimitExceededError,
)
from source.errors.upload import UploadFileMissingError, UploadFileTooLargeError, UploadNotFoundError, UploadStorageError, UploadUnsupportedFormatError
from source.repositories.admin_audit_log import AdminAuditLogRepository
from source.repositories.address import AddressRepository
from source.repositories.category import CategoryRepository
from source.repositories.delivery_settings import DeliverySettingsRepository
from source.repositories.delivery_zone import DeliveryZoneRepository
from source.repositories.discount import DiscountCategoryRepository, DiscountProductRepository, DiscountRepository
from source.repositories.integration_log import IntegrationLogRepository
from source.repositories.order import OrderRepository
from source.repositories.order_item import OrderItemRepository
from source.repositories.order_status_history import OrderStatusHistoryRepository
from source.repositories.notification import NotificationRepository
from source.repositories.payment import PaymentRepository
from source.repositories.pickup_point import PickupPointRepository
from source.repositories.product import ProductRepository
from source.repositories.product_availability_log import ProductAvailabilityLogRepository
from source.repositories.product_image import ProductImageRepository
from source.repositories.promo_code import PromoCodeCategoryRepository, PromoCodeProductRepository, PromoCodeUsageRepository
from source.repositories.promo_code import PromoCodeRepository
from source.repositories.refresh_token import RefreshTokenRepository
from source.repositories.role import PermissionRepository, RoleRepository, UserRoleRepository
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
from source.schemas.pydantic.discount import (
    AdminDiscountCreateRequest,
    AdminDiscountDetailResponse,
    AdminDiscountListQueryParams,
    AdminDiscountListResponse,
    AdminDiscountStatusResponse,
    AdminDiscountUpdateRequest,
    MessageResponse as AdminDiscountMessageResponse,
)
from source.schemas.pydantic.delivery import (
    AdminDeliverySettingsResponse,
    AdminDeliverySettingsUpdateRequest,
    AdminDeliveryZoneCreateRequest,
    AdminDeliveryZoneListQueryParams,
    AdminDeliveryZoneListResponse,
    AdminDeliveryZoneResponse,
    AdminDeliveryZoneUpdateRequest,
    AdminPickupPointCreateRequest,
    AdminPickupPointListQueryParams,
    AdminPickupPointListResponse,
    AdminPickupPointResponse,
    AdminPickupPointUpdateRequest,
    MessageResponse as AdminDeliveryMessageResponse,
)
from source.schemas.pydantic.admin_role import AdminRoleListResponse
from source.schemas.pydantic.admin_category import (
    AdminCategoryCreateRequest,
    AdminCategoryDetailResponse,
    AdminCategoryListQueryParams,
    AdminCategoryListResponse,
    AdminCategorySortRequest,
    AdminCategoryUpdateRequest,
    MessageResponse as AdminCategoryMessageResponse,
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
from source.schemas.pydantic.admin_staff import (
    AdminStaffCreateRequest,
    AdminStaffDetailResponse,
    AdminStaffListQueryParams,
    AdminStaffListResponse,
    AdminStaffRoleUpdateRequest,
    AdminStaffUpdateRequest,
    MessageResponse as AdminStaffMessageResponse,
)
from source.schemas.pydantic.order import (
    AdminOrderActionResponse,
    AdminOrderCancelRequest,
    AdminOrderConfirmRequest,
    AdminOrderDetailResponse,
    AdminOrderListQueryParams,
    AdminOrderListResponse,
    AdminOrderPrintResponse,
    AdminOrderStatusResponse,
    AdminOrderStatusUpdateRequest,
    AdminOrderSync1CRequest,
    AdminOrderSync1CResponse,
    AdminOrderUpdateRequest,
    AdminOrderUpdateResponse,
)
from source.schemas.pydantic.promo_code import (
    AdminPromoCodeCreateRequest,
    AdminPromoCodeDetailResponse,
    AdminPromoCodeListQueryParams,
    AdminPromoCodeListResponse,
    AdminPromoCodeUpdateRequest,
    MessageResponse as AdminPromoCodeMessageResponse,
)
from source.schemas.pydantic.user import (
    AdminUserBlockRequest,
    AdminUserBlockResponse,
    AdminUserDetailResponse,
    AdminUserListQueryParams,
    AdminUserListResponse,
    AdminUserOrdersQueryParams,
    AdminUserOrdersResponse,
    AdminUserUnblockRequest,
    AdminUserUpdateRequest,
    AdminUserUpdateResponse,
)
from source.services.category_cache import CategoryCacheService
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.auth_cache import AuthCacheService
from source.services.admin_auth_cache import AdminAuthCacheService
from source.services.admin_category import AdminCategoryService, CategoryTreeService
from source.services.admin_category_cache import AdminCategoryCacheService
from source.services.admin_discount import AdminDiscountService, DiscountConflictService
from source.services.admin_discount_cache import AdminDiscountCacheService
from source.services.admin_dashboard import AdminDashboardService
from source.services.admin_dashboard_cache import AdminDashboardCacheService
from source.services.admin_delivery import AdminDeliveryService
from source.services.admin_delivery_cache import AdminDeliveryCacheService
from source.services.delivery_cache import DeliveryCacheService
from source.services.admin_order import AdminOrderService
from source.services.admin_order_print import AdminOrderPrintService
from source.services.admin_product import AdminProductService
from source.services.admin_product_cache import AdminProductCacheService
from source.services.admin_product_image import AdminProductImageService
from source.services.admin_promo_code import AdminPromoCodeService
from source.services.admin_staff import AdminStaffService
from source.services.admin_staff_cache import AdminStaffCacheService
from source.services.admin_user import AdminUserService
from source.services.product_cache import ProductCacheService
from source.services.order_cache import OrderCacheService
from source.services.order_status import OrderStatusService
from source.services.notifications import EmailService, NotificationService, TelegramNotificationService
from source.services.one_c import OneCIntegrationService
from source.services.payment import PaymentService
from source.services.password import PasswordService
from source.services.profile_cache import ProfileCacheService
from source.services.promo_code import PromoCodeService
from source.services.redis import RedisService
from source.services.refresh_token import RefreshTokenService
from source.services.role import RoleService
from source.services.storage import StorageService
from source.services.stock import StockMovementService, StockService
from source.services.upload import UploadService
from source.services.user_cache import UserCacheService

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


@router.post(
    "/delivery/zones",
    response_model=AdminDeliveryZoneResponse,
    response_model_exclude={"is_deleted", "updated_at"},
    status_code=status.HTTP_201_CREATED,
)
@inject
async def create_admin_delivery_zone(
    request: Request,
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:create")),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    delivery_zone_repository: FromDishka[DeliveryZoneRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDeliveryZoneResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.create_zone(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminDeliveryZoneCreateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_cache_service=delivery_cache_service,
            delivery_zone_repository=delivery_zone_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        await commiter.rollback()
        detail = "Неверные входные данные"
        first_error = error.errors()[0] if error.errors() else None
        if first_error is not None and isinstance(first_error.get("msg"), str):
            detail = first_error["msg"].replace("Value error, ", "", 1)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from error
    except ValueError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except DeliveryZoneAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Зона доставки с таким названием уже существует") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.patch(
    "/delivery/zones/{zone_id}",
    response_model=AdminDeliveryZoneResponse,
    response_model_exclude={"is_deleted", "created_at"},
    status_code=status.HTTP_200_OK,
)
@inject
async def update_admin_delivery_zone(
    request: Request,
    zone_id: int = Path(...),
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:update")),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    delivery_zone_repository: FromDishka[DeliveryZoneRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDeliveryZoneResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.update_zone(
            session=session,
            redis_service=redis_service,
            user=current_user,
            zone_id=zone_id,
            data=AdminDeliveryZoneUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_cache_service=delivery_cache_service,
            delivery_zone_repository=delivery_zone_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        await commiter.rollback()
        detail = "Неверные входные данные"
        first_error = error.errors()[0] if error.errors() else None
        if first_error is not None and isinstance(first_error.get("msg"), str):
            detail = first_error["msg"].replace("Value error, ", "", 1)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from error
    except EmptyDeliveryZoneUpdateError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не передано ни одного поля для обновления") from error
    except ValueError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except DeliveryZoneNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Зона доставки не найдена") from error
    except DeliveryZoneAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Зона доставки с таким названием уже существует") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.delete(
    "/delivery/zones/{zone_id}",
    response_model=AdminDeliveryMessageResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def delete_admin_delivery_zone(
    request: Request,
    zone_id: int = Path(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:delete")),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    delivery_zone_repository: FromDishka[DeliveryZoneRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDeliveryMessageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.delete_zone(
            session=session,
            redis_service=redis_service,
            user=current_user,
            zone_id=zone_id,
            commiter=commiter,
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_cache_service=delivery_cache_service,
            delivery_zone_repository=delivery_zone_repository,
            order_repository=order_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except DeliveryZoneNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Зона доставки не найдена") from error
    except DeliveryZoneActiveOrdersError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Зона доставки используется в активных заказах") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.post(
    "/delivery/pickup-points",
    response_model=AdminPickupPointResponse,
    response_model_exclude={"is_deleted", "updated_at"},
    status_code=status.HTTP_201_CREATED,
)
@inject
async def create_admin_delivery_pickup_point(
    request: Request,
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:create")),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminPickupPointResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.create_pickup_point(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminPickupPointCreateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_cache_service=delivery_cache_service,
            pickup_point_repository=pickup_point_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        await commiter.rollback()
        detail = "Неверные входные данные"
        first_error = error.errors()[0] if error.errors() else None
        if first_error is not None and isinstance(first_error.get("msg"), str):
            detail = first_error["msg"].replace("Value error, ", "", 1)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except PickupPointAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Точка самовывоза с таким адресом уже существует") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.patch(
    "/delivery/pickup-points/{point_id}",
    response_model=AdminPickupPointResponse,
    response_model_exclude={"is_deleted", "created_at"},
    status_code=status.HTTP_200_OK,
)
@inject
async def update_admin_delivery_pickup_point(
    request: Request,
    point_id: int = Path(...),
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:update")),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminPickupPointResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.update_pickup_point(
            session=session,
            redis_service=redis_service,
            user=current_user,
            point_id=point_id,
            data=AdminPickupPointUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_cache_service=delivery_cache_service,
            pickup_point_repository=pickup_point_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        await commiter.rollback()
        detail = "Неверные входные данные"
        first_error = error.errors()[0] if error.errors() else None
        if first_error is not None and isinstance(first_error.get("msg"), str):
            detail = first_error["msg"].replace("Value error, ", "", 1)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from error
    except EmptyPickupPointUpdateError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не передано ни одного поля для обновления") from error
    except ValueError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except PickupPointAdminNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Точка самовывоза не найдена") from error
    except PickupPointAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Точка самовывоза с таким адресом уже существует") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get(
    "/delivery/pickup-points",
    response_model=AdminPickupPointListResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_admin_delivery_pickup_points(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    city: str | None = Query(default=None, min_length=1, max_length=100),
    is_active: bool | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:read")),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
) -> AdminPickupPointListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.get_pickup_points(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=AdminPickupPointListQueryParams(
                page=page,
                limit=limit,
                q=q,
                city=city,
                is_active=is_active,
                include_deleted=include_deleted,
            ),
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            pickup_point_repository=pickup_point_repository,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get("/delivery/zones", response_model=AdminDeliveryZoneListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_delivery_zones(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    city: str | None = Query(default=None, min_length=1, max_length=100),
    is_active: bool | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:read")),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    delivery_zone_repository: FromDishka[DeliveryZoneRepository] = None,
) -> AdminDeliveryZoneListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.get_zones(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=AdminDeliveryZoneListQueryParams(
                page=page,
                limit=limit,
                q=q,
                city=city,
                is_active=is_active,
                include_deleted=include_deleted,
            ),
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_zone_repository=delivery_zone_repository,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get("/delivery/settings", response_model=AdminDeliverySettingsResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_delivery_settings(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:read")),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    delivery_settings_repository: FromDishka[DeliverySettingsRepository] = None,
) -> AdminDeliverySettingsResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.get_settings(
            session=session,
            redis_service=redis_service,
            user=current_user,
            commiter=commiter,
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_settings_repository=delivery_settings_repository,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.patch("/delivery/settings", response_model=AdminDeliverySettingsResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_delivery_settings(
    request: Request,
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(require_permission("admin:delivery:update")),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_delivery_service: FromDishka[AdminDeliveryService] = None,
    admin_delivery_cache_service: FromDishka[AdminDeliveryCacheService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    delivery_settings_repository: FromDishka[DeliverySettingsRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDeliverySettingsResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_delivery_service.update_settings(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminDeliverySettingsUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            admin_delivery_cache_service=admin_delivery_cache_service,
            delivery_cache_service=delivery_cache_service,
            delivery_settings_repository=delivery_settings_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные настройки доставки") from error
    except EmptyDeliverySettingsUpdateError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не передано ни одного поля для обновления") from error
    except ValueError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get("/roles", response_model=AdminRoleListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_roles(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    role_service: FromDishka[RoleService] = None,
    permission_service: FromDishka[PermissionService] = None,
    role_repository: FromDishka[RoleRepository] = None,
    permission_repository: FromDishka[PermissionRepository] = None,
) -> AdminRoleListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await role_service.get_admin_roles(
            session=session,
            redis_service=redis_service,
            user=current_user,
            permission_service=permission_service,
            role_repository=role_repository,
            permission_repository=permission_repository,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.get("/promo-codes", response_model=AdminPromoCodeListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_promo_codes(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    page: str = Query(default="1"),
    limit: str = Query(default="50"),
    q: str | None = Query(default=None),
    is_active: str | None = Query(default=None),
    discount_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_promo_code_service: FromDishka[AdminPromoCodeService] = None,
    permission_service: FromDishka[PermissionService] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    promo_code_usage_repository: FromDishka[PromoCodeUsageRepository] = None,
) -> AdminPromoCodeListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminPromoCodeListQueryParams(
            page=page,
            limit=limit,
            q=q,
            is_active=is_active,
            discount_type=discount_type,
            date_from=date_from,
            date_to=date_to,
        )
        return await admin_promo_code_service.get_promo_codes(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            promo_code_repository=promo_code_repository,
            promo_code_usage_repository=promo_code_usage_repository,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.post("/promo-codes", response_model=AdminPromoCodeDetailResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_admin_promo_code(
    request: Request,
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_promo_code_service: FromDishka[AdminPromoCodeService] = None,
    permission_service: FromDishka[PermissionService] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    promo_code_product_repository: FromDishka[PromoCodeProductRepository] = None,
    promo_code_category_repository: FromDishka[PromoCodeCategoryRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminPromoCodeDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_promo_code_service.create_promo_code(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminPromoCodeCreateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            promo_code_repository=promo_code_repository,
            promo_code_product_repository=promo_code_product_repository,
            promo_code_category_repository=promo_code_category_repository,
            product_repository=product_repository,
            category_repository=category_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные промокода") from error
    except ValueError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные промокода") from error
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
    except CategoryNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error
    except PromoCodeAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Промокод с таким code уже существует") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get("/promo-codes/{promo_code_id}", response_model=AdminPromoCodeDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_promo_code_detail(
    promo_code_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_promo_code_service: FromDishka[AdminPromoCodeService] = None,
    permission_service: FromDishka[PermissionService] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    promo_code_usage_repository: FromDishka[PromoCodeUsageRepository] = None,
    promo_code_product_repository: FromDishka[PromoCodeProductRepository] = None,
    promo_code_category_repository: FromDishka[PromoCodeCategoryRepository] = None,
) -> AdminPromoCodeDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_promo_code_service.get_promo_code_detail(
            session=session,
            redis_service=redis_service,
            user=current_user,
            promo_code_id=promo_code_id,
            permission_service=permission_service,
            promo_code_repository=promo_code_repository,
            promo_code_usage_repository=promo_code_usage_repository,
            promo_code_product_repository=promo_code_product_repository,
            promo_code_category_repository=promo_code_category_repository,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except PromoCodeNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Промокод не найден") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.patch("/promo-codes/{promo_code_id}", response_model=AdminPromoCodeDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_promo_code(
    request: Request,
    payload: dict = Body(...),
    promo_code_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_promo_code_service: FromDishka[AdminPromoCodeService] = None,
    permission_service: FromDishka[PermissionService] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    promo_code_usage_repository: FromDishka[PromoCodeUsageRepository] = None,
    promo_code_product_repository: FromDishka[PromoCodeProductRepository] = None,
    promo_code_category_repository: FromDishka[PromoCodeCategoryRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminPromoCodeDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_promo_code_service.update_promo_code(
            session=session,
            redis_service=redis_service,
            user=current_user,
            promo_code_id=promo_code_id,
            data=AdminPromoCodeUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            promo_code_repository=promo_code_repository,
            promo_code_usage_repository=promo_code_usage_repository,
            promo_code_product_repository=promo_code_product_repository,
            promo_code_category_repository=promo_code_category_repository,
            product_repository=product_repository,
            category_repository=category_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные промокода") from error
    except EmptyPromoCodeUpdateError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не передано ни одного поля для изменения") from error
    except ValueError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные промокода") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except PromoCodeNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Промокод не найден") from error
    except ProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except CategoryNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error
    except PromoCodeAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Промокод с таким code уже существует") from error
    except PromoCodeUsageLimitExceededError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="usage_limit меньше уже использованного количества") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.delete("/promo-codes/{promo_code_id}", response_model=AdminPromoCodeMessageResponse, status_code=status.HTTP_200_OK)
@inject
async def delete_admin_promo_code(
    request: Request,
    promo_code_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_promo_code_service: FromDishka[AdminPromoCodeService] = None,
    permission_service: FromDishka[PermissionService] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminPromoCodeMessageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_promo_code_service.delete_promo_code(
            session=session,
            redis_service=redis_service,
            user=current_user,
            promo_code_id=promo_code_id,
            commiter=commiter,
            permission_service=permission_service,
            promo_code_repository=promo_code_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
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
    except PromoCodeNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Промокод не найден") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get("/discounts", response_model=AdminDiscountListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_discounts(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    page: str = Query(default="1"),
    limit: str = Query(default="50"),
    q: str | None = Query(default=None),
    type: str | None = Query(default=None),
    discount_type: str | None = Query(default=None),
    is_active: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_discount_service: FromDishka[AdminDiscountService] = None,
    admin_discount_cache_service: FromDishka[AdminDiscountCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
) -> AdminDiscountListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminDiscountListQueryParams(
            page=page,
            limit=limit,
            q=q,
            type=type,
            discount_type=discount_type,
            is_active=is_active,
            date_from=date_from,
            date_to=date_to,
        )
        return await admin_discount_service.get_discounts(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            discount_repository=discount_repository,
            admin_discount_cache_service=admin_discount_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные query params") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.post("/discounts", response_model=AdminDiscountDetailResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_admin_discount(
    request: Request,
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_discount_service: FromDishka[AdminDiscountService] = None,
    admin_discount_cache_service: FromDishka[AdminDiscountCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
    discount_product_repository: FromDishka[DiscountProductRepository] = None,
    discount_category_repository: FromDishka[DiscountCategoryRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    discount_conflict_service: FromDishka[DiscountConflictService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDiscountDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_discount_service.create_discount(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminDiscountCreateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            discount_repository=discount_repository,
            discount_product_repository=discount_product_repository,
            discount_category_repository=discount_category_repository,
            product_repository=product_repository,
            category_repository=category_repository,
            discount_conflict_service=discount_conflict_service,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_discount_cache_service=admin_discount_cache_service,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные скидки") from error
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
    except CategoryNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error
    except Exception:
        await commiter.rollback()
        raise


@router.get("/discounts/{discount_id}", response_model=AdminDiscountDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_discount_detail(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    discount_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_discount_service: FromDishka[AdminDiscountService] = None,
    admin_discount_cache_service: FromDishka[AdminDiscountCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
    discount_product_repository: FromDishka[DiscountProductRepository] = None,
    discount_category_repository: FromDishka[DiscountCategoryRepository] = None,
) -> AdminDiscountDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_discount_service.get_discount_detail(
            session=session,
            redis_service=redis_service,
            user=current_user,
            discount_id=discount_id,
            permission_service=permission_service,
            discount_repository=discount_repository,
            discount_product_repository=discount_product_repository,
            discount_category_repository=discount_category_repository,
            admin_discount_cache_service=admin_discount_cache_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except DiscountNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скидка не найдена") from error


@router.patch("/discounts/{discount_id}", response_model=AdminDiscountDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_discount(
    request: Request,
    payload: dict = Body(...),
    discount_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_discount_service: FromDishka[AdminDiscountService] = None,
    admin_discount_cache_service: FromDishka[AdminDiscountCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
    discount_product_repository: FromDishka[DiscountProductRepository] = None,
    discount_category_repository: FromDishka[DiscountCategoryRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    discount_conflict_service: FromDishka[DiscountConflictService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDiscountDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_discount_service.update_discount(
            session=session,
            redis_service=redis_service,
            user=current_user,
            discount_id=discount_id,
            data=AdminDiscountUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            discount_repository=discount_repository,
            discount_product_repository=discount_product_repository,
            discount_category_repository=discount_category_repository,
            product_repository=product_repository,
            category_repository=category_repository,
            discount_conflict_service=discount_conflict_service,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_discount_cache_service=admin_discount_cache_service,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные скидки") from error
    except EmptyDiscountUpdateError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не передано ни одного поля для изменения") from error
    except ValueError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные скидки") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except DiscountNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скидка не найдена") from error
    except ProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except CategoryNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error
    except DiscountConflictError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Конфликт скидок") from error
    except Exception:
        await commiter.rollback()
        raise


@router.post("/discounts/{discount_id}/activate", response_model=AdminDiscountStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def activate_admin_discount(
    request: Request,
    discount_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_discount_service: FromDishka[AdminDiscountService] = None,
    admin_discount_cache_service: FromDishka[AdminDiscountCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
    discount_product_repository: FromDishka[DiscountProductRepository] = None,
    discount_category_repository: FromDishka[DiscountCategoryRepository] = None,
    discount_conflict_service: FromDishka[DiscountConflictService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDiscountStatusResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_discount_service.activate_discount(
            session=session,
            redis_service=redis_service,
            user=current_user,
            discount_id=discount_id,
            commiter=commiter,
            permission_service=permission_service,
            discount_repository=discount_repository,
            discount_product_repository=discount_product_repository,
            discount_category_repository=discount_category_repository,
            discount_conflict_service=discount_conflict_service,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_discount_cache_service=admin_discount_cache_service,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
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
    except DiscountNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скидка не найдена") from error
    except DiscountExpiredError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Срок действия скидки уже истёк") from error
    except DiscountConflictError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Конфликт скидок") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.post("/discounts/{discount_id}/deactivate", response_model=AdminDiscountStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def deactivate_admin_discount(
    request: Request,
    discount_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_discount_service: FromDishka[AdminDiscountService] = None,
    admin_discount_cache_service: FromDishka[AdminDiscountCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDiscountStatusResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_discount_service.deactivate_discount(
            session=session,
            redis_service=redis_service,
            user=current_user,
            discount_id=discount_id,
            commiter=commiter,
            permission_service=permission_service,
            discount_repository=discount_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_discount_cache_service=admin_discount_cache_service,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
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
    except DiscountNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скидка не найдена") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.delete("/discounts/{discount_id}", response_model=AdminDiscountMessageResponse, status_code=status.HTTP_200_OK)
@inject
async def delete_admin_discount(
    request: Request,
    discount_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_discount_service: FromDishka[AdminDiscountService] = None,
    admin_discount_cache_service: FromDishka[AdminDiscountCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    discount_repository: FromDishka[DiscountRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminDiscountMessageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_discount_service.delete_discount(
            session=session,
            redis_service=redis_service,
            user=current_user,
            discount_id=discount_id,
            commiter=commiter,
            permission_service=permission_service,
            discount_repository=discount_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_discount_cache_service=admin_discount_cache_service,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
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
    except DiscountNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скидка не найдена") from error
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.get("/staff", response_model=AdminStaffListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_staff(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    page: str = Query(default="1"),
    limit: str = Query(default="50"),
    q: str | None = Query(default=None),
    role: str | None = Query(default=None),
    is_active: str | None = Query(default=None),
    is_blocked: str | None = Query(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_staff_service: FromDishka[AdminStaffService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
) -> AdminStaffListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminStaffListQueryParams(
            page=page,
            limit=limit,
            q=q,
            role=role,
            is_active=is_active,
            is_blocked=is_blocked,
        )
        return await admin_staff_service.get_staff_list(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            user_repository=user_repository,
            admin_staff_cache_service=admin_staff_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные параметры запроса") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.post("/staff", response_model=AdminStaffDetailResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_admin_staff(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_staff_service: FromDishka[AdminStaffService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    password_service: FromDishka[PasswordService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminStaffDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_staff_service.create_staff(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminStaffCreateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            user_repository=user_repository,
            password_service=password_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_staff_cache_service=admin_staff_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные сотрудника") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminStaffInvalidRoleError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Недопустимая роль") from error
    except UserPhoneAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким телефоном уже существует") from error
    except UserEmailAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким email уже существует") from error
    except Exception:
        await commiter.rollback()
        raise


@router.get("/staff/{staff_id}", response_model=AdminStaffDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_staff_detail(
    staff_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_staff_service: FromDishka[AdminStaffService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
) -> AdminStaffDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_staff_service.get_staff_detail(
            session=session,
            redis_service=redis_service,
            user=current_user,
            staff_id=staff_id,
            permission_service=permission_service,
            user_repository=user_repository,
            admin_staff_cache_service=admin_staff_cache_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminStaffNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден") from error


@router.patch(
    "/staff/{staff_id}",
    response_model=AdminStaffDetailResponse,
    response_model_exclude={"permissions", "is_blocked", "last_login_at", "created_at"},
    status_code=status.HTTP_200_OK,
)
@inject
async def update_admin_staff(
    request: Request,
    payload: dict = Body(...),
    staff_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_staff_service: FromDishka[AdminStaffService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
    admin_auth_cache_service: FromDishka[AdminAuthCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminStaffDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_staff_service.update_staff(
            session=session,
            redis_service=redis_service,
            user=current_user,
            staff_id=staff_id,
            data=AdminStaffUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            user_repository=user_repository,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_staff_cache_service=admin_staff_cache_service,
            admin_auth_cache_service=admin_auth_cache_service,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные сотрудника") from error
    except EmptyAdminStaffUpdateError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не передано ни одного поля для изменения") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminStaffNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден") from error
    except UserPhoneAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким телефоном уже существует") from error
    except UserEmailAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким email уже существует") from error
    except LastActiveAdminDeactivationError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя деактивировать последнего администратора",
        ) from error
    except Exception:
        await commiter.rollback()
        raise


@router.patch(
    "/staff/{staff_id}/role",
    response_model=AdminStaffDetailResponse,
    response_model_exclude={"email", "phone", "is_active", "is_blocked", "last_login_at", "created_at"},
    status_code=status.HTTP_200_OK,
)
@inject
async def change_admin_staff_role(
    request: Request,
    payload: dict = Body(...),
    staff_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_staff_service: FromDishka[AdminStaffService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
    admin_auth_cache_service: FromDishka[AdminAuthCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    role_repository: FromDishka[RoleRepository] = None,
    user_role_repository: FromDishka[UserRoleRepository] = None,
    refresh_token_repository: FromDishka[RefreshTokenRepository] = None,
    refresh_token_service: FromDishka[RefreshTokenService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminStaffDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_staff_service.change_role(
            session=session,
            redis_service=redis_service,
            user=current_user,
            staff_id=staff_id,
            data=AdminStaffRoleUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            user_repository=user_repository,
            role_repository=role_repository,
            user_role_repository=user_role_repository,
            refresh_token_repository=refresh_token_repository,
            refresh_token_service=refresh_token_service,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_staff_cache_service=admin_staff_cache_service,
            admin_auth_cache_service=admin_auth_cache_service,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные роли") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminStaffNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден") from error
    except AdminRoleNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Роль не найдена") from error
    except AdminStaffInvalidRoleError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимая роль") from error
    except AdminStaffSelfRoleChangeError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Нельзя менять свою роль") from error
    except LastActiveAdminRoleChangeError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя изменить роль последнего администратора",
        ) from error
    except Exception:
        await commiter.rollback()
        raise


@router.delete("/staff/{staff_id}", response_model=AdminStaffMessageResponse, status_code=status.HTTP_200_OK)
@inject
async def delete_admin_staff(
    request: Request,
    staff_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_staff_service: FromDishka[AdminStaffService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
    admin_auth_cache_service: FromDishka[AdminAuthCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    refresh_token_repository: FromDishka[RefreshTokenRepository] = None,
    refresh_token_service: FromDishka[RefreshTokenService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminStaffMessageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_staff_service.delete_staff(
            session=session,
            redis_service=redis_service,
            user=current_user,
            staff_id=staff_id,
            commiter=commiter,
            permission_service=permission_service,
            user_repository=user_repository,
            refresh_token_repository=refresh_token_repository,
            refresh_token_service=refresh_token_service,
            audit_log_service=audit_log_service,
            admin_audit_log_repository=admin_audit_log_repository,
            admin_staff_cache_service=admin_staff_cache_service,
            admin_auth_cache_service=admin_auth_cache_service,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
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
    except AdminStaffNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден") from error
    except AdminStaffSelfDeleteError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Нельзя удалить самого себя") from error
    except LastActiveAdminDeleteError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя удалить последнего администратора",
        ) from error
    except Exception:
        await commiter.rollback()
        raise


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


@router.post("/categories", response_model=AdminCategoryDetailResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_admin_category(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_category_service: FromDishka[AdminCategoryService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    upload_repository: FromDishka[UploadRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
) -> AdminCategoryDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_category_service.create_category(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminCategoryCreateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            category_repository=category_repository,
            upload_repository=upload_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            audit_log_service=audit_log_service,
            category_cache_service=category_cache_service,
            admin_category_cache_service=admin_category_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except CategoryNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Родительская категория не найдена") from error
    except UploadNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено") from error
    except CategorySlugAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug уже занят") from error


@router.patch(
    "/categories/sort",
    response_model=AdminCategoryMessageResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def sort_admin_categories(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_category_service: FromDishka[AdminCategoryService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    category_tree_service: FromDishka[CategoryTreeService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
) -> AdminCategoryMessageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_category_service.sort_categories(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=AdminCategorySortRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            category_repository=category_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            audit_log_service=audit_log_service,
            category_tree_service=category_tree_service,
            category_cache_service=category_cache_service,
            admin_category_cache_service=admin_category_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except CategoryCycleError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Циклическая вложенность запрещена") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except CategoryNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error


@router.get(
    "/categories/{category_id}",
    response_model=AdminCategoryDetailResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def get_admin_category_detail(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    category_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_category_service: FromDishka[AdminCategoryService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    upload_repository: FromDishka[UploadRepository] = None,
) -> AdminCategoryDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_category_service.get_category_detail(
            session=session,
            redis_service=redis_service,
            user=current_user,
            category_id=category_id,
            permission_service=permission_service,
            category_repository=category_repository,
            product_repository=product_repository,
            upload_repository=upload_repository,
            admin_category_cache_service=admin_category_cache_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except CategoryNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error


@router.patch(
    "/categories/{category_id}",
    response_model=AdminCategoryDetailResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
@inject
async def update_admin_category(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    category_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_category_service: FromDishka[AdminCategoryService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    category_tree_service: FromDishka[CategoryTreeService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    upload_repository: FromDishka[UploadRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
) -> AdminCategoryDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_category_service.update_category(
            session=session,
            redis_service=redis_service,
            user=current_user,
            category_id=category_id,
            data=AdminCategoryUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            category_repository=category_repository,
            upload_repository=upload_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            audit_log_service=audit_log_service,
            category_tree_service=category_tree_service,
            category_cache_service=category_cache_service,
            admin_category_cache_service=admin_category_cache_service,
            product_cache_service=product_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except ValueError as error:
        detail = "Нет полей для обновления" if str(error) == "No fields to update" else "Неверные данные"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from error
    except CategoryCycleError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Циклическая вложенность запрещена") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except CategoryNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error
    except UploadNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено") from error
    except CategorySlugAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug уже занят") from error


@router.delete(
    "/categories/{category_id}",
    response_model=AdminCategoryMessageResponse,
    status_code=status.HTTP_200_OK,
)
@inject
async def delete_admin_category(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    category_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    commiter: FromDishka[Commiter] = None,
    admin_category_service: FromDishka[AdminCategoryService] = None,
    admin_category_cache_service: FromDishka[AdminCategoryCacheService] = None,
    category_cache_service: FromDishka[CategoryCacheService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    category_repository: FromDishka[CategoryRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
) -> AdminCategoryMessageResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_category_service.delete_category(
            session=session,
            redis_service=redis_service,
            user=current_user,
            category_id=category_id,
            commiter=commiter,
            permission_service=permission_service,
            category_repository=category_repository,
            product_repository=product_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            audit_log_service=audit_log_service,
            category_cache_service=category_cache_service,
            admin_category_cache_service=admin_category_cache_service,
            product_cache_service=product_cache_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except CategoryNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена") from error
    except CategoryHasActiveProductsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="В категории есть товары") from error
    except CategoryHasActiveChildrenError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="У категории есть дочерние категории") from error


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


@router.get("/orders", response_model=AdminOrderListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_orders(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    page: str = Query(default="1"),
    limit: str = Query(default="50"),
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    payment_status: str | None = Query(default=None),
    payment_method: str | None = Query(default=None),
    delivery_type: str | None = Query(default=None),
    sync_status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    min_amount: str | None = Query(default=None),
    max_amount: str | None = Query(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_order_service: FromDishka[AdminOrderService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> AdminOrderListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminOrderListQueryParams(
            page=page,
            limit=limit,
            q=q,
            status=status_filter,
            payment_status=payment_status,
            payment_method=payment_method,
            delivery_type=delivery_type,
            sync_status=sync_status,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount,
        )
        return await admin_order_service.get_orders(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            order_repository=order_repository,
            order_cache_service=order_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные параметры запроса") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.get("/users", response_model=AdminUserListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_users(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    page: str = Query(default="1"),
    limit: str = Query(default="50"),
    q: str | None = Query(default=None),
    is_active: str | None = Query(default=None),
    is_blocked: str | None = Query(default=None),
    is_deleted: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_user_service: FromDishka[AdminUserService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> AdminUserListResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminUserListQueryParams(
            page=page,
            limit=limit,
            q=q,
            is_active=is_active,
            is_blocked=is_blocked,
            is_deleted=is_deleted,
            date_from=date_from,
            date_to=date_to,
        )
        return await admin_user_service.get_users(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=query,
            permission_service=permission_service,
            user_repository=user_repository,
            order_repository=order_repository,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные параметры запроса") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_user_detail(
    user_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_user_service: FromDishka[AdminUserService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> AdminUserDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_user_service.get_user_detail(
            session=session,
            redis_service=redis_service,
            user=current_user,
            user_id=user_id,
            permission_service=permission_service,
            user_repository=user_repository,
            address_repository=address_repository,
            order_repository=order_repository,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminUserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден") from error


@router.get("/users/{user_id}/orders", response_model=AdminUserOrdersResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_user_orders(
    user_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    page: str = Query(default="1"),
    limit: str = Query(default="20"),
    status_filter: str | None = Query(default=None, alias="status"),
    payment_status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_user_service: FromDishka[AdminUserService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> AdminUserOrdersResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        query = AdminUserOrdersQueryParams(
            page=page,
            limit=limit,
            status=status_filter,
            payment_status=payment_status,
            date_from=date_from,
            date_to=date_to,
        )
        return await admin_user_service.get_user_orders(
            session=session,
            redis_service=redis_service,
            user=current_user,
            user_id=user_id,
            query=query,
            permission_service=permission_service,
            user_repository=user_repository,
            order_repository=order_repository,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные параметры запроса") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminUserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден") from error


@router.patch("/users/{user_id}", response_model=AdminUserUpdateResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_user(
    payload: dict = Body(...),
    user_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_user_service: FromDishka[AdminUserService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    user_cache_service: FromDishka[UserCacheService] = None,
    auth_cache_service: FromDishka[AuthCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
) -> AdminUserUpdateResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_user_service.update_user(
            session=session,
            redis_service=redis_service,
            user=current_user,
            user_id=user_id,
            data=AdminUserUpdateRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            user_repository=user_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            profile_cache_service=profile_cache_service,
            admin_staff_cache_service=admin_staff_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные пользователя") from error
    except EmptyUserProfileUpdateError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не передано ни одного поля для изменения") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminUserNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден") from error
    except UserPhoneAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким телефоном уже существует") from error
    except UserEmailAlreadyExistsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким email уже существует") from error
    except Exception:
        await commiter.rollback()
        raise


@router.patch("/users/{user_id}/block", response_model=AdminUserBlockResponse, status_code=status.HTTP_200_OK)
@inject
async def block_admin_user(
    payload: dict = Body(...),
    user_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_user_service: FromDishka[AdminUserService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    refresh_token_repository: FromDishka[RefreshTokenRepository] = None,
    refresh_token_service: FromDishka[RefreshTokenService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    user_cache_service: FromDishka[UserCacheService] = None,
    auth_cache_service: FromDishka[AuthCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
) -> AdminUserBlockResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_user_service.block_user(
            session=session,
            redis_service=redis_service,
            user=current_user,
            user_id=user_id,
            data=AdminUserBlockRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            user_repository=user_repository,
            refresh_token_repository=refresh_token_repository,
            refresh_token_service=refresh_token_service,
            admin_audit_log_repository=admin_audit_log_repository,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            profile_cache_service=profile_cache_service,
            admin_staff_cache_service=admin_staff_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные блокировки") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminUserNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден") from error
    except AdminUserAlreadyBlockedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь уже заблокирован") from error
    except Exception:
        await commiter.rollback()
        raise


@router.patch("/users/{user_id}/unblock", response_model=AdminUserBlockResponse, status_code=status.HTTP_200_OK)
@inject
async def unblock_admin_user(
    payload: dict = Body(...),
    user_id: int = Path(..., gt=0),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_user_service: FromDishka[AdminUserService] = None,
    permission_service: FromDishka[PermissionService] = None,
    user_repository: FromDishka[UserRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    user_cache_service: FromDishka[UserCacheService] = None,
    auth_cache_service: FromDishka[AuthCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    admin_staff_cache_service: FromDishka[AdminStaffCacheService] = None,
) -> AdminUserBlockResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_user_service.unblock_user(
            session=session,
            redis_service=redis_service,
            user=current_user,
            user_id=user_id,
            data=AdminUserUnblockRequest.model_validate(payload),
            commiter=commiter,
            permission_service=permission_service,
            user_repository=user_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            profile_cache_service=profile_cache_service,
            admin_staff_cache_service=admin_staff_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные разблокировки") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminUserNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден") from error
    except AdminUserNotBlockedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь не заблокирован") from error
    except Exception:
        await commiter.rollback()
        raise


@router.get("/orders/{order_id}", response_model=AdminOrderDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_order_detail(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    order_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_order_service: FromDishka[AdminOrderService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
) -> AdminOrderDetailResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_order_service.get_order_detail(
            session=session,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            permission_service=permission_service,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            address_repository=address_repository,
            pickup_point_repository=pickup_point_repository,
            payment_repository=payment_repository,
            order_status_history_repository=order_status_history_repository,
            order_cache_service=order_cache_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error


@router.get("/orders/{order_id}/print", status_code=status.HTTP_200_OK)
@inject
async def get_admin_order_print(
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    order_id: int = Path(ge=1),
    format: str = Query(default="html"),
    session: FromDishka[AsyncSession] = None,
    admin_order_print_service: FromDishka[AdminOrderPrintService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
):
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        response_format = admin_order_print_service.validate_format(format=format)
        print_data = await admin_order_print_service.get_print_data(
            session=session,
            user=current_user,
            order_id=order_id,
            permission_service=permission_service,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            address_repository=address_repository,
            pickup_point_repository=pickup_point_repository,
        )
        if response_format == "json":
            return print_data
        return HTMLResponse(content=admin_order_print_service.render_html(data=print_data))
    except OrderPrintFormatError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный format") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error


@router.post("/orders/{order_id}/confirm", response_model=AdminOrderActionResponse, status_code=status.HTTP_200_OK)
@inject
async def confirm_admin_order(
    payload: dict = Body(default_factory=dict),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    order_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_order_service: FromDishka[AdminOrderService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
    stock_service: FromDishka[StockService] = None,
    notification_service: FromDishka[NotificationService] = None,
    notification_repository: FromDishka[NotificationRepository] = None,
    email_service: FromDishka[EmailService] = None,
    telegram_service: FromDishka[TelegramNotificationService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
) -> AdminOrderActionResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_order_service.confirm_order(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            data=AdminOrderConfirmRequest.model_validate(payload),
            permission_service=permission_service,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            product_repository=product_repository,
            order_status_history_repository=order_status_history_repository,
            stock_service=stock_service,
            notification_service=notification_service,
            notification_repository=notification_repository,
            email_service=email_service,
            telegram_service=telegram_service,
            order_cache_service=order_cache_service,
            profile_cache_service=profile_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderConfirmNotAllowedError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заказ нельзя подтвердить в текущем статусе") from error
    except (OrderItemsNotFoundError, OrderUnavailableItemsError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Проблемы с остатками") from error


@router.post("/orders/{order_id}/cancel", response_model=AdminOrderActionResponse, status_code=status.HTTP_200_OK)
@inject
async def cancel_admin_order(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    order_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_order_service: FromDishka[AdminOrderService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_usage_repository: FromDishka[PromoCodeUsageRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    stock_service: FromDishka[StockService] = None,
    promo_code_service: FromDishka[PromoCodeService] = None,
    payment_service: FromDishka[PaymentService] = None,
    one_c_integration_service: FromDishka[OneCIntegrationService] = None,
    notification_service: FromDishka[NotificationService] = None,
    email_service: FromDishka[EmailService] = None,
    telegram_service: FromDishka[TelegramNotificationService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
) -> AdminOrderActionResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_order_service.cancel_order(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            data=AdminOrderCancelRequest.model_validate(payload),
            permission_service=permission_service,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            product_repository=product_repository,
            promo_code_usage_repository=promo_code_usage_repository,
            payment_repository=payment_repository,
            order_status_history_repository=order_status_history_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            stock_service=stock_service,
            promo_code_service=promo_code_service,
            payment_service=payment_service,
            one_c_integration_service=one_c_integration_service,
            notification_service=notification_service,
            email_service=email_service,
            telegram_service=telegram_service,
            order_cache_service=order_cache_service,
            profile_cache_service=profile_cache_service,
            product_cache_service=product_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAlreadyCancelledError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заказ уже отменён") from error
    except OrderCompletedCancellationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Завершённый заказ нельзя отменить") from error


@router.post("/orders/{order_id}/sync-1c", response_model=AdminOrderSync1CResponse, status_code=status.HTTP_200_OK)
@inject
async def sync_admin_order_1c(
    payload: dict = Body(default_factory=dict),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    order_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_order_service: FromDishka[AdminOrderService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    integration_log_repository: FromDishka[IntegrationLogRepository] = None,
    one_c_integration_service: FromDishka[OneCIntegrationService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
) -> AdminOrderSync1CResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_order_service.sync_order_1c(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            data=AdminOrderSync1CRequest.model_validate(payload),
            permission_service=permission_service,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            payment_repository=payment_repository,
            integration_log_repository=integration_log_repository,
            one_c_integration_service=one_c_integration_service,
            order_cache_service=order_cache_service,
            profile_cache_service=profile_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except OneCIntegrationDisabledError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Интеграция с 1С отключена") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAlreadySyncedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Заказ уже синхронизирован") from error
    except OneCSyncError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка 1С") from error


@router.patch("/orders/{order_id}/status", response_model=AdminOrderStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_order_status(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    order_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_order_service: FromDishka[AdminOrderService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
    order_status_service: FromDishka[OrderStatusService] = None,
    notification_service: FromDishka[NotificationService] = None,
    notification_repository: FromDishka[NotificationRepository] = None,
    email_service: FromDishka[EmailService] = None,
    telegram_service: FromDishka[TelegramNotificationService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
) -> AdminOrderStatusResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        return await admin_order_service.update_status(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            data=AdminOrderStatusUpdateRequest.model_validate(payload),
            permission_service=permission_service,
            order_repository=order_repository,
            order_status_history_repository=order_status_history_repository,
            order_status_service=order_status_service,
            notification_service=notification_service,
            notification_repository=notification_repository,
            email_service=email_service,
            telegram_service=telegram_service,
            order_cache_service=order_cache_service,
            profile_cache_service=profile_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый статус") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderInvalidStatusError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый статус") from error
    except OrderStatusTransitionError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый переход статуса") from error


@router.patch("/orders/{order_id}", response_model=AdminOrderUpdateResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_order(
    payload: dict = Body(...),
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    order_id: int = Path(ge=1),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_order_service: FromDishka[AdminOrderService] = None,
    permission_service: FromDishka[PermissionService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
) -> AdminOrderUpdateResponse:
    if token_payload.get("token_type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован")
    try:
        admin_order_service.validate_update_payload_fields(payload=payload)
        return await admin_order_service.update_order(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            data=AdminOrderUpdateRequest.model_validate(payload),
            permission_service=permission_service,
            order_repository=order_repository,
            admin_audit_log_repository=admin_audit_log_repository,
            order_cache_service=order_cache_service,
            profile_cache_service=profile_cache_service,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные данные") from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except EmptyOrderUpdateError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нет полей для обновления") from error
    except OrderFieldNotEditableError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Поле нельзя редактировать") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderUpdateNotAllowedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Заказ нельзя редактировать в текущем статусе") from error


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
