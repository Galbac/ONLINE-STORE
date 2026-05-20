from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.admin_category import (
    AdminCategoryListItemResponse,
    AdminCategoryListQueryParams,
    AdminCategoryListResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminCategoryService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:categories:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_categories(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminCategoryListQueryParams,
        permission_service,
        category_repository,
        product_repository,
        admin_category_cache_service,
    ) -> AdminCategoryListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_categories = await admin_category_cache_service.get_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_categories is not None:
            return cached_categories

        categories = await category_repository.admin_get_list(session=session, query=normalized_query)
        items = [
            AdminCategoryListItemResponse(
                id=category.id,
                name=category.name,
                slug=category.slug,
                parent_id=category.parent_id,
                image_url=category.image_url,
                sort_order=category.sort_order,
                is_active=category.is_active,
                is_deleted=category.is_deleted,
                products_count=await product_repository.count_by_category_id(
                    session=session,
                    category_id=category.id,
                ),
                created_at=category.created_date,
            )
            for category in categories
        ]
        total = await category_repository.admin_count(session=session, query=normalized_query)
        response = AdminCategoryListResponse.build(
            items=items,
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await admin_category_cache_service.set_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.categories.admin_list_cache_ttl_seconds,
        )
        return response
