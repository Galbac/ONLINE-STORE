from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import settings
from source.errors.auth import (
    AddressAccessDeniedError,
    AddressActiveOrderExistsError,
    AddressNotFoundError,
    CurrentUserNotFoundError,
    EmptyUserProfileUpdateError,
    InactiveUserError,
    UserAddressesLimitExceededError,
)
from source.repositories.address import AddressRepository
from source.repositories.order import OrderRepository
from source.repositories.user import UserRepository
from source.schemas.pydantic.profile import (
    AddressCreateRequest,
    AddressListQueryParams,
    AddressListResponse,
    AddressResponse,
    AddressUpdateRequest,
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

    async def delete_address(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        profile_cache_service: ProfileCacheService,
        user_repository: UserRepository,
        address_repository: AddressRepository,
        order_repository: OrderRepository,
        user_id: int,
        address_id: int,
    ) -> None:
        user = await user_repository.get_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        address = await address_repository.get_by_id(
            session=session,
            address_id=address_id,
        )
        if address is None:
            raise AddressNotFoundError
        if address.user_id != user.id:
            raise AddressAccessDeniedError
        if address.is_deleted:
            raise AddressNotFoundError

        if await order_repository.has_active_orders_by_address_id(
            session=session,
            address_id=address.id,
        ):
            raise AddressActiveOrderExistsError

        was_default = address.is_default
        await address_repository.soft_delete(session=session, address=address)
        if was_default:
            next_default_address = await address_repository.get_first_active_by_user_id(
                session=session,
                user_id=user.id,
                exclude_address_id=address.id,
            )
            if next_default_address is not None:
                await address_repository.set_default(
                    session=session,
                    address=next_default_address,
                )

        await profile_cache_service.invalidate_addresses(
            redis_service=redis_service,
            user_id=user.id,
        )
        await profile_cache_service.delete_summary(
            redis_service=redis_service,
            user_id=user.id,
        )

    async def update_address(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        profile_cache_service: ProfileCacheService,
        user_repository: UserRepository,
        address_repository: AddressRepository,
        user_id: int,
        address_id: int,
        data: AddressUpdateRequest,
    ) -> AddressResponse:
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise EmptyUserProfileUpdateError

        user = await user_repository.get_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        address = await address_repository.get_by_id(
            session=session,
            address_id=address_id,
        )
        if address is None:
            raise AddressNotFoundError
        if address.user_id != user.id:
            raise AddressAccessDeniedError
        if address.is_deleted:
            raise AddressNotFoundError

        requested_default = update_data.get("is_default")
        if requested_default is True:
            await address_repository.unset_default_by_user_id(
                session=session,
                user_id=user.id,
            )
        elif requested_default is False and address.is_default:
            addresses_count = await address_repository.count_by_user_id(
                session=session,
                user_id=user.id,
                include_deleted=False,
            )
            if addresses_count <= 1:
                data = data.model_copy(update={"is_default": True})

        response = await address_repository.update(
            session=session,
            address=address,
            data=data,
        )
        await profile_cache_service.invalidate_addresses(
            redis_service=redis_service,
            user_id=user.id,
        )
        await profile_cache_service.delete_summary(
            redis_service=redis_service,
            user_id=user.id,
        )
        return response

    async def create_address(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        profile_cache_service: ProfileCacheService,
        user_repository: UserRepository,
        address_repository: AddressRepository,
        user_id: int,
        data: AddressCreateRequest,
    ) -> AddressResponse:
        user = await user_repository.get_by_id(session=session, user_id=user_id)
        if user is None:
            raise CurrentUserNotFoundError
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        addresses_count = await address_repository.count_by_user_id(
            session=session,
            user_id=user.id,
            include_deleted=False,
        )
        if addresses_count >= settings.profile_addresses.user_addresses_limit:
            raise UserAddressesLimitExceededError

        is_default = data.is_default or addresses_count == 0
        if is_default:
            await address_repository.unset_default_by_user_id(
                session=session,
                user_id=user.id,
            )

        response = await address_repository.create(
            session=session,
            user_id=user.id,
            data=data,
            is_default=is_default,
        )
        await profile_cache_service.invalidate_addresses(
            redis_service=redis_service,
            user_id=user.id,
        )
        await profile_cache_service.delete_summary(
            redis_service=redis_service,
            user_id=user.id,
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
