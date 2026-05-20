from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.discount import (
    AdminDiscountListItemResponse,
    AdminDiscountListQueryParams,
    AdminDiscountListResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminDiscountService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:discounts:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_discounts(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminDiscountListQueryParams,
        permission_service,
        discount_repository,
        admin_discount_cache_service,
    ) -> AdminDiscountListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_discounts = await admin_discount_cache_service.get_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_discounts is not None:
            return cached_discounts

        discounts = await discount_repository.admin_get_list(session=session, query=normalized_query)
        total = await discount_repository.admin_count(session=session, query=normalized_query)
        response = AdminDiscountListResponse.build(
            items=[self._build_discount_response(discount=discount) for discount in discounts],
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await admin_discount_cache_service.set_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.discounts.admin_list_cache_ttl_seconds,
        )
        return response

    def _build_discount_response(self, *, discount) -> AdminDiscountListItemResponse:
        return AdminDiscountListItemResponse(
            id=discount.id,
            name=discount.name,
            type=discount.type,
            discount_type=discount.discount_type,
            discount_value=discount.discount_value,
            is_active=discount.is_active,
            starts_at=discount.starts_at,
            ends_at=discount.ends_at,
            created_at=discount.created_date,
        )
