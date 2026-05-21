from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.promo_code import (
    AdminPromoCodeListItemResponse,
    AdminPromoCodeListQueryParams,
    AdminPromoCodeListResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminPromoCodeService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:promo_codes:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_promo_codes(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminPromoCodeListQueryParams,
        permission_service,
        promo_code_repository,
        promo_code_usage_repository,
    ) -> AdminPromoCodeListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        cache_key = self._list_key(query_hash=build_query_hash(normalized_query.model_dump()))
        cached_promo_codes = await redis_service.get(cache_key)
        if cached_promo_codes is not None:
            if isinstance(cached_promo_codes, bytes):
                cached_promo_codes = cached_promo_codes.decode("utf-8")
            return AdminPromoCodeListResponse.model_validate_json(cached_promo_codes)

        promo_codes = await promo_code_repository.admin_get_list(session=session, query=normalized_query)
        total = await promo_code_repository.admin_count(session=session, query=normalized_query)
        usage_counts = await promo_code_usage_repository.count_grouped_by_promo_code_ids(
            session=session,
            promo_code_ids=[promo_code.id for promo_code in promo_codes],
        )
        response = AdminPromoCodeListResponse.build(
            items=[
                self._build_promo_code_response(
                    promo_code=promo_code,
                    usage_count=usage_counts.get(promo_code.id, 0),
                )
                for promo_code in promo_codes
            ],
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await redis_service.set(
            cache_key,
            response.model_dump_json(),
            ttl_seconds=settings.promo_codes.admin_list_cache_ttl_seconds,
        )
        return response

    def _list_key(self, *, query_hash: str) -> str:
        return f"admin:promo_codes:list:{query_hash}"

    def _build_promo_code_response(self, *, promo_code, usage_count: int) -> AdminPromoCodeListItemResponse:
        return AdminPromoCodeListItemResponse(
            id=promo_code.id,
            code=promo_code.code,
            name=getattr(promo_code, "name", None),
            discount_type=promo_code.discount_type,
            discount_value=promo_code.discount_value,
            min_order_amount=promo_code.min_order_amount,
            usage_limit=promo_code.usage_limit,
            usage_count=usage_count,
            user_usage_limit=promo_code.per_user_usage_limit,
            is_active=promo_code.is_active,
            starts_at=promo_code.starts_at,
            ends_at=promo_code.ends_at,
        )
