from datetime import datetime
from decimal import Decimal

from source.config.settings import settings
from source.errors.auth import (
    AdminAuthAccessDeniedError,
    AdminUserAlreadyBlockedError,
    AdminUserNotFoundError,
    AdminUserNotBlockedError,
    EmptyUserProfileUpdateError,
    InactiveUserError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.user import (
    AdminUserAddressResponse,
    AdminUserBlockRequest,
    AdminUserBlockResponse,
    AdminUserDetailResponse,
    AdminUserListItemResponse,
    AdminUserListQueryParams,
    AdminUserListResponse,
    AdminUserOrderShortResponse,
    AdminUserOrdersQueryParams,
    AdminUserOrdersResponse,
    AdminUserUnblockRequest,
    AdminUserUpdateRequest,
    AdminUserUpdateResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminUserService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:users:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:users:update" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_block_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:users:block" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_user_orders_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        permissions = permission_service.get_user_permissions(role=user.role)
        if "admin:users:read" not in permissions and "admin:orders:read" not in permissions:
            raise AdminAuthAccessDeniedError

    async def get_users(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminUserListQueryParams,
        permission_service,
        user_repository,
        order_repository,
    ) -> AdminUserListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cache_key = f"admin:users:list:{query_hash}"
        cached_users = await redis_service.get(cache_key)
        if cached_users is not None:
            if isinstance(cached_users, bytes):
                cached_users = cached_users.decode("utf-8")
            return AdminUserListResponse.model_validate_json(cached_users)

        customers = await user_repository.admin_get_customers(session=session, query=normalized_query)
        total = await user_repository.admin_count_customers(session=session, query=normalized_query)
        stats_by_user_id = await order_repository.get_user_stats_grouped(
            session=session,
            user_ids=[customer.id for customer in customers],
        )
        items = [
            self._build_user_response(customer=customer, stats=stats_by_user_id.get(customer.id))
            for customer in customers
        ]
        response = AdminUserListResponse.build(
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await redis_service.set(
            cache_key,
            response.model_dump_json(),
            ttl_seconds=settings.admin_users.list_cache_ttl_seconds,
        )
        return response

    async def get_user_detail(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        user_id: int,
        permission_service,
        user_repository,
        address_repository,
        order_repository,
    ) -> AdminUserDetailResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cache_key = f"admin:users:detail:{user_id}"
        cached_user = await redis_service.get(cache_key)
        if cached_user is not None:
            if isinstance(cached_user, bytes):
                cached_user = cached_user.decode("utf-8")
            return AdminUserDetailResponse.model_validate_json(cached_user)

        customer = await user_repository.get_by_id(session=session, user_id=user_id)
        if customer is None:
            raise AdminUserNotFoundError

        addresses = await address_repository.get_by_user_id(
            session=session,
            user_id=customer.id,
            include_deleted=False,
            limit=50,
            offset=0,
        )
        stats = await order_repository.get_user_stats(session=session, user_id=customer.id)
        recent_orders = await order_repository.get_recent_by_user_id(
            session=session,
            user_id=customer.id,
            limit=5,
        )
        response = self._build_user_detail_response(
            customer=customer,
            addresses=addresses,
            stats=stats,
            recent_orders=recent_orders,
        )
        await redis_service.set(
            cache_key,
            response.model_dump_json(),
            ttl_seconds=settings.admin_users.detail_cache_ttl_seconds,
        )
        return response

    async def get_user_orders(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        user_id: int,
        query: AdminUserOrdersQueryParams,
        permission_service,
        user_repository,
        order_repository,
    ) -> AdminUserOrdersResponse:
        self._check_user_orders_read_permission(user=user, permission_service=permission_service)

        customer = await user_repository.get_by_id(session=session, user_id=user_id)
        if customer is None:
            raise AdminUserNotFoundError

        query_hash = build_query_hash(query.model_dump())
        cache_key = f"admin:users:{user_id}:orders:{query_hash}"
        cached_orders = await redis_service.get(cache_key)
        if cached_orders is not None:
            if isinstance(cached_orders, bytes):
                cached_orders = cached_orders.decode("utf-8")
            return AdminUserOrdersResponse.model_validate_json(cached_orders)

        orders = await order_repository.get_by_user_id(session=session, user_id=user_id, query=query)
        total = await order_repository.count_by_user_id(session=session, user_id=user_id, query=query)
        response = AdminUserOrdersResponse.build(
            items=[self._build_order_response(order=order) for order in orders],
            total=total,
            page=query.page,
            limit=query.limit,
        )
        await redis_service.set(
            cache_key,
            response.model_dump_json(),
            ttl_seconds=settings.admin_users.detail_cache_ttl_seconds,
        )
        return response

    async def update_user(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        user_id: int,
        data: AdminUserUpdateRequest,
        commiter,
        permission_service,
        user_repository,
        admin_audit_log_repository,
        user_cache_service,
        auth_cache_service,
        profile_cache_service,
        admin_staff_cache_service=None,
    ) -> AdminUserUpdateResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyUserProfileUpdateError

        customer = await user_repository.get_by_id(session=session, user_id=user_id)
        if customer is None:
            raise AdminUserNotFoundError

        if "phone" in update_fields and update_fields["phone"] != customer.phone:
            existing_user = await user_repository.get_by_phone(session=session, phone=update_fields["phone"])
            if existing_user is not None and existing_user.id != customer.id:
                raise UserPhoneAlreadyExistsError
        if "email" in update_fields and update_fields["email"] != customer.email:
            email = update_fields["email"]
            if email is not None:
                existing_user = await user_repository.get_by_email(session=session, email=email)
                if existing_user is not None and existing_user.id != customer.id:
                    raise UserEmailAlreadyExistsError

        before = {
            field: getattr(customer, field)
            for field in update_fields
        }
        for field, value in update_fields.items():
            setattr(customer, field, value)
        customer.updated_date = datetime.now(settings.tz)
        updated_user = await user_repository.update(session=session, user=customer)

        changes = {
            field: {
                "old": str(before[field]) if before[field] is not None else None,
                "new": str(getattr(updated_user, field)) if getattr(updated_user, field) is not None else None,
            }
            for field in update_fields
            if before[field] != getattr(updated_user, field)
        }
        await admin_audit_log_repository.create(
            session=session,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_user_update",
            status="success",
            details={
                "target_user_id": updated_user.id,
                "changes": changes,
            },
        )
        await commiter.commit()

        await self._invalidate_user_cache(
            redis_service=redis_service,
            user_id=updated_user.id,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            profile_cache_service=profile_cache_service,
            admin_staff_cache_service=admin_staff_cache_service,
        )

        return AdminUserUpdateResponse(
            id=updated_user.id,
            name=updated_user.name,
            phone=updated_user.phone,
            email=updated_user.email,
            is_active=updated_user.is_active,
            updated_at=updated_user.updated_date,
        )

    async def block_user(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        user_id: int,
        data: AdminUserBlockRequest,
        commiter,
        permission_service,
        user_repository,
        refresh_token_repository,
        refresh_token_service,
        admin_audit_log_repository,
        user_cache_service,
        auth_cache_service,
        profile_cache_service,
        admin_staff_cache_service=None,
    ) -> AdminUserBlockResponse:
        self._check_block_permission(user=user, permission_service=permission_service)

        customer = await user_repository.get_by_id(session=session, user_id=user_id)
        if customer is None:
            raise AdminUserNotFoundError
        if customer.is_blocked:
            raise AdminUserAlreadyBlockedError

        blocked_user = await user_repository.block(
            session=session,
            user=customer,
            blocked_at=datetime.now(settings.tz),
            blocked_by=user.id,
            block_reason=data.reason,
        )
        revoked_tokens_count = 0
        if data.revoke_sessions:
            revoked_tokens_count = await refresh_token_service.revoke_all_user_tokens(
                session=session,
                refresh_token_repository=refresh_token_repository,
                user_id=blocked_user.id,
            )

        await admin_audit_log_repository.create(
            session=session,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_user_block",
            status="success",
            details={
                "target_user_id": blocked_user.id,
                "reason": data.reason,
                "revoke_sessions": data.revoke_sessions,
                "revoked_tokens_count": revoked_tokens_count,
            },
        )
        await commiter.commit()

        await self._invalidate_user_cache(
            redis_service=redis_service,
            user_id=blocked_user.id,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            profile_cache_service=profile_cache_service,
            admin_staff_cache_service=admin_staff_cache_service,
        )

        return AdminUserBlockResponse(
            message="Пользователь заблокирован",
            user_id=blocked_user.id,
            is_blocked=blocked_user.is_blocked,
        )

    async def unblock_user(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        user_id: int,
        data: AdminUserUnblockRequest,
        commiter,
        permission_service,
        user_repository,
        admin_audit_log_repository,
        user_cache_service,
        auth_cache_service,
        profile_cache_service,
        admin_staff_cache_service=None,
    ) -> AdminUserBlockResponse:
        self._check_block_permission(user=user, permission_service=permission_service)

        customer = await user_repository.get_by_id(session=session, user_id=user_id)
        if customer is None:
            raise AdminUserNotFoundError
        if not customer.is_blocked:
            raise AdminUserNotBlockedError

        unblocked_user = await user_repository.unblock(
            session=session,
            user=customer,
            unblocked_at=datetime.now(settings.tz),
            unblocked_by=user.id,
            unblock_reason=data.reason,
        )
        await admin_audit_log_repository.create(
            session=session,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_user_unblock",
            status="success",
            details={
                "target_user_id": unblocked_user.id,
                "reason": data.reason,
            },
        )
        await commiter.commit()

        await self._invalidate_user_cache(
            redis_service=redis_service,
            user_id=unblocked_user.id,
            user_cache_service=user_cache_service,
            auth_cache_service=auth_cache_service,
            profile_cache_service=profile_cache_service,
            admin_staff_cache_service=admin_staff_cache_service,
        )

        return AdminUserBlockResponse(
            message="Пользователь разблокирован",
            user_id=unblocked_user.id,
            is_blocked=unblocked_user.is_blocked,
        )

    def _build_user_response(self, *, customer, stats) -> AdminUserListItemResponse:
        return AdminUserListItemResponse(
            id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            is_active=customer.is_active,
            is_blocked=customer.is_blocked,
            orders_count=stats.orders_count if stats is not None else 0,
            total_spent=stats.total_spent if stats is not None else Decimal("0.00"),
            created_at=customer.created_date,
        )

    def _build_user_detail_response(self, *, customer, addresses, stats, recent_orders) -> AdminUserDetailResponse:
        return AdminUserDetailResponse(
            id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            is_active=customer.is_active,
            is_blocked=customer.is_blocked,
            is_deleted=customer.is_deleted,
            orders_count=stats.orders_count,
            total_spent=stats.total_spent,
            addresses=[self._build_address_response(address=address) for address in addresses],
            recent_orders=[self._build_order_response(order=order) for order in recent_orders],
            created_at=customer.created_date,
        )

    def _build_address_response(self, *, address) -> AdminUserAddressResponse:
        return AdminUserAddressResponse(
            id=address.id,
            title=address.title,
            city=address.city,
            street=address.street,
            house=address.house,
            building=address.building,
            apartment=address.apartment,
            entrance=address.entrance,
            floor=address.floor,
            intercom=address.intercom,
            comment=address.comment,
            is_default=address.is_default,
            created_at=address.created_at,
        )

    def _build_order_response(self, *, order) -> AdminUserOrderShortResponse:
        return AdminUserOrderShortResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            payment_status=order.payment_status,
            delivery_type=order.delivery_type,
            final_price=order.final_price,
            items_count=order.items_count,
            created_at=order.created_at,
        )

    async def _invalidate_user_cache(
        self,
        *,
        redis_service: RedisService,
        user_id: int,
        user_cache_service,
        auth_cache_service,
        profile_cache_service,
        admin_staff_cache_service=None,
    ) -> None:
        await redis_service.delete_by_pattern("admin:users:*")
        if admin_staff_cache_service is not None:
            await admin_staff_cache_service.invalidate_all(redis_service=redis_service)
        await user_cache_service.delete_user_me_cache(redis_service=redis_service, user_id=user_id)
        await auth_cache_service.delete_current_user_cache(redis_service=redis_service, user_id=user_id)
        await profile_cache_service.delete_summary(redis_service=redis_service, user_id=user_id)
