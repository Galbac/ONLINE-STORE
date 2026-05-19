from dishka.integrations.fastapi import FromDishka, inject
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, verify_access_token
from source.db.models.user import User
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError, InvalidCredentialsError
from source.repositories.order import OrderRepository
from source.repositories.product import ProductRepository
from source.repositories.user import UserRepository
from source.schemas.pydantic.admin_dashboard import (
    AdminDashboardResponse,
    AdminLowStockQueryParams,
    AdminLowStockResponse,
    AdminSalesQueryParams,
    AdminSalesResponse,
)
from source.schemas.pydantic.admin_product import AdminProductListQueryParams, AdminProductListResponse
from source.services.admin_auth import PermissionService
from source.services.admin_dashboard import AdminDashboardService
from source.services.admin_dashboard_cache import AdminDashboardCacheService
from source.services.admin_product import AdminProductService
from source.services.admin_product_cache import AdminProductCacheService
from source.services.redis import RedisService

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


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
