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
    return await resolve_current_user(
        authorization=authorization,
        session=session,
        redis_service=redis_service,
    )


async def resolve_current_user(
    *,
    authorization: str | None,
    session: AsyncSession,
    redis_service: RedisService | None = None,
) -> User:
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

    jti = payload.get("jti")
    if settings.change_password.jwt_access_blacklist_enabled and redis_service is not None and jti:
        if await redis_service.get(f"auth:blacklist:access:{jti}") is not None:
            raise_unauthorized()

    user_id = payload.get("user_id")
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
