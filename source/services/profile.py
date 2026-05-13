from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.auth import CurrentUserNotFoundError, InactiveUserError
from source.repositories.address import AddressRepository
from source.repositories.order import OrderRepository
from source.repositories.user import UserRepository
from source.schemas.pydantic.profile import (
    AddressListQueryParams,
    AddressListResponse,
    ProfileStatsResponse,
    ProfileSummaryResponse,
    ProfileUserResponse,
)
from source.services.profile_cache import ProfileCacheService
from source.services.redis import RedisService


class ProfileService:
    async def get_profile_summary(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        profile_cache_service: ProfileCacheService,
        user_repository: UserRepository,
        address_repository: AddressRepository,
        order_repository: OrderRepository,
        user_id: int,
    ) -> ProfileSummaryResponse:
        cached_summary = await profile_cache_service.get_summary(
            redis_service=redis_service,
            user_id=user_id,
        )
        if cached_summary is not None:
            return cached_summary

        user = await user_repository.get_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        default_address = await address_repository.get_default_by_user_id(
            session=session,
            user_id=user.id,
        )
        addresses_count = await address_repository.count_by_user_id(
            session=session,
            user_id=user.id,
        )
        orders_count = await order_repository.count_by_user_id(
            session=session,
            user_id=user.id,
        )
        active_order = await order_repository.get_active_by_user_id(
            session=session,
            user_id=user.id,
        )
        recent_orders = await order_repository.get_recent_by_user_id(
            session=session,
            user_id=user.id,
            limit=5,
        )

        response = ProfileSummaryResponse(
            user=ProfileUserResponse(
                id=user.id,
                name=user.name,
                phone=user.phone,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                is_verified=False,
            ),
            stats=ProfileStatsResponse(
                orders_count=orders_count,
                addresses_count=addresses_count,
            ),
            default_address=default_address,
            active_order=active_order,
            recent_orders=recent_orders,
        )
        await profile_cache_service.set_summary(
            redis_service=redis_service,
            user_id=user.id,
            response=response,
            ttl_seconds=settings.profile_summary.cache_ttl_seconds,
        )
        return response

    async def get_user_addresses(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        profile_cache_service: ProfileCacheService,
        user_repository: UserRepository,
        address_repository: AddressRepository,
        user_id: int,
        query: AddressListQueryParams,
    ) -> AddressListResponse:
        cached_addresses = await profile_cache_service.get_addresses(
            redis_service=redis_service,
            user_id=user_id,
            include_deleted=query.include_deleted,
            limit=query.limit,
            offset=query.offset,
        )
        if cached_addresses is not None:
            return cached_addresses

        user = await user_repository.get_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        items = await address_repository.get_by_user_id(
            session=session,
            user_id=user.id,
            include_deleted=query.include_deleted,
            limit=query.limit,
            offset=query.offset,
        )
        total = await address_repository.count_by_user_id(
            session=session,
            user_id=user.id,
            include_deleted=query.include_deleted,
        )
        response = AddressListResponse(
            items=items,
            total=total,
            limit=query.limit,
            offset=query.offset,
        )
        await profile_cache_service.set_addresses(
            redis_service=redis_service,
            user_id=user.id,
            include_deleted=query.include_deleted,
            limit=query.limit,
            offset=query.offset,
            response=response,
            ttl_seconds=settings.profile_addresses.cache_ttl_seconds,
        )
        return response
