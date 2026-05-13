from datetime import datetime

from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.db.models.refresh_token import RefreshToken
from source.db.models.user import User
from source.errors.auth import (
    ActiveOrdersExistError,
    CurrentUserNotFoundError,
    EmptyUserProfileUpdateError,
    InvalidCurrentPasswordError,
    InactiveUserError,
    UserDeleteConfirmationRequiredError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.user import UserMeDeleteRequest, UserMeResponse, UserMeUpdateRequest
from source.services.auth import AuthService
from source.services.auth_cache import AuthCacheService
from source.services.redis import RedisService
from source.services.user_cache import UserCacheService


class UserService:
    async def get_current_user_profile(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        user_cache_service: UserCacheService,
        user_id: int,
    ) -> UserMeResponse:
        cached_user = await user_cache_service.get_user_me_cache(
            redis_service=redis_service,
            user_id=user_id,
        )
        if cached_user is not None:
            return cached_user

        user = await self._get_user_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        response = self._build_user_me_response(user)
        await user_cache_service.set_user_me_cache(
            redis_service=redis_service,
            user_id=user.id,
            response=response,
            ttl_seconds=settings.user_me.cache_ttl_seconds,
        )
        return response

    async def update_current_user_profile(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        user_cache_service: UserCacheService,
        auth_cache_service: AuthCacheService,
        user_id: int,
        data: UserMeUpdateRequest,
    ) -> UserMeResponse:
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise EmptyUserProfileUpdateError

        user = await self._get_user_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        phone = update_data.get("phone")
        if phone is not None and phone != user.phone:
            await self._ensure_phone_is_unique(
                session=session,
                phone=phone,
                current_user_id=user.id,
            )
            user.phone = phone

        email = update_data.get("email")
        if "email" in update_data and email != user.email:
            if email is not None:
                await self._ensure_email_is_unique(
                    session=session,
                    email=email,
                    current_user_id=user.id,
                )
            user.email = email

        name = update_data.get("name")
        if name is not None:
            user.name = name

        user.updated_date = datetime.now(settings.tz)
        session.add(user)
        await session.flush()
        await session.refresh(user)

        await user_cache_service.delete_user_me_cache(
            redis_service=redis_service,
            user_id=user.id,
        )
        await auth_cache_service.delete_current_user_cache(
            redis_service=redis_service,
            user_id=user.id,
        )

        return self._build_user_me_response(user)

    async def delete_current_user_account(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        user_cache_service: UserCacheService,
        auth_cache_service: AuthCacheService,
        auth_service: AuthService,
        user_id: int,
        data: UserMeDeleteRequest,
        access_token: str | None,
    ) -> None:
        if not data.confirm:
            raise UserDeleteConfirmationRequiredError

        user = await self._get_user_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if settings.user_delete.require_password and not auth_service.verify_password(data.password, user.password_hash):
            raise InvalidCurrentPasswordError
        if await self._has_active_orders(session=session, user_id=user.id):
            raise ActiveOrdersExistError

        now = datetime.now(settings.tz)
        user.is_active = False
        user.is_deleted = True
        user.deleted_at = now
        user.updated_date = now
        if settings.user_delete.anonymize:
            user.name = f"deleted_user_{user.id}"
            user.email = None

        session.add(user)
        await self._revoke_active_refresh_tokens(session=session, user_id=user.id)
        await session.flush()

        await self._delete_password_reset_tokens(redis_service=redis_service, user_id=user.id)
        await user_cache_service.delete_user_me_cache(redis_service=redis_service, user_id=user.id)
        await auth_cache_service.delete_current_user_cache(redis_service=redis_service, user_id=user.id)
        await self._blacklist_access_token_if_enabled(redis_service=redis_service, access_token=access_token)

    async def _get_user_by_id(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _ensure_phone_is_unique(
        self,
        *,
        session: AsyncSession,
        phone: str,
        current_user_id: int,
    ) -> None:
        result = await session.execute(
            select(User.id).where(
                User.phone == phone,
                User.id != current_user_id,
            ),
        )
        if result.scalar_one_or_none() is not None:
            raise UserPhoneAlreadyExistsError

    async def _ensure_email_is_unique(
        self,
        *,
        session: AsyncSession,
        email: str,
        current_user_id: int,
    ) -> None:
        result = await session.execute(
            select(User.id).where(
                User.email == email,
                User.id != current_user_id,
            ),
        )
        if result.scalar_one_or_none() is not None:
            raise UserEmailAlreadyExistsError

    async def _has_active_orders(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> bool:
        return False

    async def _revoke_active_refresh_tokens(
        self,
        *,
        session: AsyncSession,
        user_id: int,
    ) -> None:
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(settings.tz)),
        )

    async def _delete_password_reset_tokens(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
    ) -> None:
        user_key = f"password_reset:user:{user_id}"
        token_hash = await redis_service.get(user_key)
        if token_hash is not None:
            if isinstance(token_hash, bytes):
                token_hash = token_hash.decode("utf-8")
            await redis_service.delete(f"password_reset:token:{token_hash}")
        await redis_service.delete(user_key)

    async def _blacklist_access_token_if_enabled(
        self,
        *,
        redis_service: RedisService,
        access_token: str | None,
    ) -> None:
        if not settings.change_password.jwt_access_blacklist_enabled or not access_token:
            return
        try:
            payload = jwt.decode(
                token=access_token,
                key=settings.auth.jwt_secret_key,
                algorithms=[settings.auth.jwt_algorithm],
            )
        except JWTError:
            return

        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not isinstance(exp, int):
            return

        ttl_seconds = exp - int(datetime.now(settings.tz).timestamp())
        if ttl_seconds > 0:
            await redis_service.set(
                f"auth:blacklist:access:{jti}",
                "revoked",
                ttl_seconds=ttl_seconds,
            )

    def _build_user_me_response(self, user: User) -> UserMeResponse:
        return UserMeResponse(
            id=user.id,
            name=user.name,
            phone=user.phone,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            is_verified=False,
            created_at=user.created_date,
            updated_at=user.updated_date,
        )
