from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.order import AdminOrderListQueryParams, AdminOrderListResponse
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminOrderService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:orders:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_orders(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminOrderListQueryParams,
        permission_service,
        order_repository,
        order_cache_service,
    ) -> AdminOrderListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_orders = await order_cache_service.get_admin_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_orders is not None:
            return cached_orders

        items = await order_repository.admin_get_list(session=session, query=normalized_query)
        total = await order_repository.admin_count(session=session, query=normalized_query)
        response = AdminOrderListResponse.build(
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await order_cache_service.set_admin_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.orders.admin_list_cache_ttl_seconds,
        )
        return response
