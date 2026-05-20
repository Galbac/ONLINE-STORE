from decimal import Decimal

from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.user import AdminUserListItemResponse, AdminUserListQueryParams, AdminUserListResponse
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminUserService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:users:read" not in permission_service.get_user_permissions(role=user.role):
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

    def _build_user_response(self, *, customer, stats) -> AdminUserListItemResponse:
        return AdminUserListItemResponse(
            id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            is_active=customer.is_active,
            is_blocked=not customer.is_active,
            orders_count=stats.orders_count if stats is not None else 0,
            total_spent=stats.total_spent if stats is not None else Decimal("0.00"),
            created_at=customer.created_date,
        )
