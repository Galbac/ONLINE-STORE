from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, verify_access_token
from source.db.models.user import User
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError, InvalidCredentialsError
from source.repositories.order import OrderRepository
from source.repositories.product import ProductRepository
from source.repositories.user import UserRepository
from source.schemas.pydantic.admin_dashboard import AdminDashboardResponse
from source.services.admin_auth import PermissionService
from source.services.admin_dashboard import AdminDashboardService
from source.services.admin_dashboard_cache import AdminDashboardCacheService
from source.services.redis import RedisService

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


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
