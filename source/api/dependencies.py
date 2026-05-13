from typing import Any

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.user import User
from source.services.redis import RedisService


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
    return user


def raise_unauthorized() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Пользователь не авторизован",
        headers={"WWW-Authenticate": "Bearer"},
    )
