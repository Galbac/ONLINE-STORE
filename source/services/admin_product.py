from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.admin_product import AdminProductListQueryParams, AdminProductListResponse
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminProductService:
    async def get_products(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminProductListQueryParams,
        permission_service,
        product_repository,
        admin_product_cache_service,
    ) -> AdminProductListResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:products:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_products = await admin_product_cache_service.get_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_products is not None:
            return cached_products

        items = await product_repository.admin_get_list(session=session, query=normalized_query)
        total = await product_repository.admin_count(session=session, query=normalized_query)
        response = AdminProductListResponse.build(
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await admin_product_cache_service.set_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.products.admin_list_cache_ttl_seconds,
        )
        return response
