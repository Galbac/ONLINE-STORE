from typing import Any
from secrets import compare_digest

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, Header, HTTPException, Query, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.user import User
from source.db.models.choises.enum import UserRole
from source.services.admin_auth import PermissionService, STAFF_ROLES
from source.services.redis import RedisService
from source.db.models.pickup_point import PickupPoint


@inject
async def select_store_context(
    store_id: int | None = Query(default=None, ge=1),
    x_store_id: int | None = Header(default=None, ge=1),
    session: FromDishka[AsyncSession] = None,
) -> None:
    selected_id = store_id if store_id is not None else x_store_id
    if selected_id is not None:
        store = await session.scalar(select(PickupPoint).where(
            PickupPoint.id == selected_id,
            PickupPoint.is_active.is_(True),
            PickupPoint.is_deleted.is_(False),
        ))
        if store is None:
            raise HTTPException(status_code=404, detail="Магазин недоступен")
    session.info["store_id"] = selected_id


@inject
async def get_current_user(
    authorization: str | None = Header(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
) -> User:
    payload = await resolve_access_token(
        authorization=authorization,
        redis_service=redis_service,
    )
    return await resolve_current_user_by_payload(
        token_payload=payload,
        session=session,
    )


@inject
async def get_current_user_optional(
    authorization: str | None = Header(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
) -> User | None:
    if not authorization:
        return None
    try:
        payload = await resolve_access_token(
            authorization=authorization,
            redis_service=redis_service,
        )
        return await resolve_current_user_by_payload(
            token_payload=payload,
            session=session,
        )
    except HTTPException:
        return None


async def require_admin_or_manager(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in {UserRole.ADMIN, UserRole.MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return current_user


def require_permission(permission: str):
    @inject
    async def dependency(
        current_user: User = Depends(get_current_user),
        permission_service: FromDishka[PermissionService] = None,
    ) -> User:
        if current_user.role not in STAFF_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        if permission not in permission_service.get_user_permissions(role=current_user.role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return current_user

    return dependency


@inject
async def verify_access_token(
    authorization: str | None = Header(default=None),
    redis_service: FromDishka[RedisService] = None,
) -> dict[str, Any]:
    return await resolve_access_token(
        authorization=authorization,
        redis_service=redis_service,
    )


async def resolve_access_token(
    *,
    authorization: str | None,
    redis_service: RedisService | None = None,
) -> dict[str, Any]:
    if not authorization:
        raise_unauthorized()

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise_unauthorized()

    try:
        payload = jwt.decode(
            token=token,
            key=settings.auth.jwt_secret_key,
            algorithms=[settings.auth.jwt_algorithm],
        )
    except JWTError:
        raise_unauthorized()

    if payload.get("token_type") != "access":
        raise_unauthorized()
    if payload.get("user_id") is None:
        raise_unauthorized()
    if payload.get("role") is None:
        raise_unauthorized()

    await check_access_token_blacklist(payload=payload, redis_service=redis_service)

    return payload


async def check_access_token_blacklist(
    *,
    payload: dict[str, Any],
    redis_service: RedisService | None = None,
) -> None:
    if not settings.change_password.jwt_access_blacklist_enabled:
        return

    jti = payload.get("jti")
    if not jti:
        raise_unauthorized()
    if redis_service is not None and await redis_service.exists(f"auth:blacklist:access:{jti}"):
        raise_unauthorized()


async def resolve_current_user(
    *,
    authorization: str | None,
    session: AsyncSession,
    redis_service: RedisService | None = None,
) -> User:
    payload = await resolve_access_token(
        authorization=authorization,
        redis_service=redis_service,
    )
    return await resolve_current_user_by_payload(
        token_payload=payload,
        session=session,
    )


async def resolve_current_user_by_payload(
    *,
    token_payload: dict[str, Any],
    session: AsyncSession,
) -> User:
    user_id = token_payload.get("user_id")
    if user_id is None:
        raise_unauthorized()

    result = await session.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise_unauthorized()
    if not user.is_active or user.is_deleted or user.is_blocked:
        raise_unauthorized()
    return user


def raise_unauthorized() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Пользователь не авторизован",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def verify_one_c_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization:
        raise_integration_unauthorized()

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise_integration_unauthorized()
    if not settings.one_c.api_token or not compare_digest(token, settings.one_c.api_token):
        raise_integration_unauthorized()


def raise_integration_unauthorized() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный integration token",
        headers={"WWW-Authenticate": "Bearer"},
    )
