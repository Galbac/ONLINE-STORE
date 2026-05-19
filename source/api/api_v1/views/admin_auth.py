from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, verify_access_token
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    AdminAuthAccessDeniedError,
    AdminAuthRateLimitExceededError,
    AdminCurrentUserNotFoundError,
    InactiveUserError,
    InvalidCredentialsError,
    RefreshTokenAlreadyRevokedError,
    RefreshTokenNotFoundError,
)
from source.repositories.admin_audit_log import AdminAuditLogRepository
from source.repositories.refresh_token import RefreshTokenRepository
from source.repositories.user import UserRepository
from source.schemas.pydantic.admin_auth import AdminAuthResponse, AdminLoginRequest, AdminLogoutRequest, AdminMeResponse, MessageResponse
from source.services.admin_auth import AdminAuthService, AuditLogService, JwtBlacklistService, JwtService, PermissionService, RateLimitService
from source.services.admin_auth_cache import AdminAuthCacheService
from source.services.redis import RedisService

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.get("/me", response_model=AdminMeResponse, status_code=status.HTTP_200_OK)
@inject
async def admin_me(
    token_payload: dict = Depends(verify_access_token),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_auth_service: FromDishka[AdminAuthService] = None,
    user_repository: FromDishka[UserRepository] = None,
    admin_auth_cache_service: FromDishka[AdminAuthCacheService] = None,
    permission_service: FromDishka[PermissionService] = None,
) -> AdminMeResponse:
    try:
        return await admin_auth_service.get_me(
            session=session,
            redis_service=redis_service,
            user_id=int(token_payload["user_id"]),
            token_payload=token_payload,
            user_repository=user_repository,
            admin_auth_cache_service=admin_auth_cache_service,
            permission_service=permission_service,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except AdminAuthAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ в админку запрещён") from error
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован") from error
    except AdminCurrentUserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден") from error


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


@router.post("/logout", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@inject
async def admin_logout(
    body: AdminLogoutRequest,
    request: Request,
    token_payload: dict = Depends(verify_access_token),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    admin_auth_service: FromDishka[AdminAuthService] = None,
    refresh_token_repository: FromDishka[RefreshTokenRepository] = None,
    jwt_blacklist_service: FromDishka[JwtBlacklistService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    admin_audit_log_repository: FromDishka[AdminAuditLogRepository] = None,
) -> MessageResponse:
    try:
        response = await admin_auth_service.logout(
            session=session,
            redis_service=redis_service,
            user=current_user,
            data=body,
            token_payload=token_payload,
            refresh_token_repository=refresh_token_repository,
            jwt_blacklist_service=jwt_blacklist_service,
            audit_log_service=audit_log_service,
            audit_log_repository=admin_audit_log_repository,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await commiter.commit()
        return response
    except RefreshTokenNotFoundError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refresh token не найден") from error
    except RefreshTokenAlreadyRevokedError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token уже отозван") from error
    except AdminAuthAccessDeniedError as error:
        await commiter.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён") from error
    except InvalidCredentialsError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован") from error
    except Exception:
        await commiter.rollback()
        raise
