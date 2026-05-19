from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.common.commiter import Commiter
from source.errors.auth import AdminAuthAccessDeniedError, AdminAuthRateLimitExceededError, InactiveUserError, InvalidCredentialsError
from source.repositories.admin_audit_log import AdminAuditLogRepository
from source.repositories.refresh_token import RefreshTokenRepository
from source.repositories.user import UserRepository
from source.schemas.pydantic.admin_auth import AdminAuthResponse, AdminLoginRequest
from source.services.admin_auth import AdminAuthService, AuditLogService, JwtService, RateLimitService
from source.services.redis import RedisService

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=AdminAuthResponse, status_code=status.HTTP_200_OK)
@inject
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_auth_service: FromDishka[AdminAuthService] = None,
    user_repository: FromDishka[UserRepository] = None,
    refresh_token_repository: FromDishka[RefreshTokenRepository] = None,
    jwt_service: FromDishka[JwtService] = None,
    rate_limit_service: FromDishka[RateLimitService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> AdminAuthResponse:
    try:
        response = await admin_auth_service.login(
            session=session,
            redis_service=redis_service,
            data=body,
            user_repository=user_repository,
            refresh_token_repository=refresh_token_repository,
            jwt_service=jwt_service,
            rate_limit_service=rate_limit_service,
            audit_log_service=audit_log_service,
            audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await commiter.commit()
        return response
    except InvalidCredentialsError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ в админку запрещён") from error
    except InactiveUserError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminAuthRateLimitExceededError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Слишком много попыток входа") from error
    except Exception:
        await commiter.rollback()
        raise
