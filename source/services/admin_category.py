from source.config.settings import settings
from source.errors.category import CategoryNotFoundError, CategorySlugAlreadyExistsError
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.upload import UploadNotFoundError
from source.schemas.pydantic.admin_category import (
    AdminCategoryCreateRequest,
    AdminCategoryDetailResponse,
    AdminCategoryListItemResponse,
    AdminCategoryListQueryParams,
    AdminCategoryListResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query
from source.utils.slug import generate_slug, normalize_slug, validate_slug


class AdminCategoryService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:categories:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_create_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:categories:create" not in permission_service.get_user_permissions(role=user.role):
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

    async def create_category(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminCategoryCreateRequest,
        commiter,
        permission_service,
        category_repository,
        upload_repository,
        admin_audit_log_repository,
        audit_log_service,
        category_cache_service,
        admin_category_cache_service,
    ) -> AdminCategoryDetailResponse:
        self._check_create_permission(user=user, permission_service=permission_service)

        slug = normalize_slug(data.slug) if data.slug is not None else generate_slug(data.name)
        if not validate_slug(slug):
            raise ValueError("Invalid slug")
        if await category_repository.get_by_slug(session=session, slug=slug) is not None:
            raise CategorySlugAlreadyExistsError

        if data.parent_id is not None:
            parent = await category_repository.get_by_id(session=session, category_id=data.parent_id)
            if parent is None:
                raise CategoryNotFoundError

        image_url = None
        if data.image_id is not None:
            image = await upload_repository.get_by_id(session=session, file_id=data.image_id)
            if image is None or image.is_deleted:
                raise UploadNotFoundError
            image_url = image.url

        category = await category_repository.create(
            session=session,
            data=data,
            slug=slug,
            image_url=image_url,
        )
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_category_create",
            status="success",
            details={
                "category_id": category.id,
                "name": category.name,
                "slug": category.slug,
                "parent_id": category.parent_id,
                "image_id": category.image_file_id,
            },
        )
        await commiter.commit()

        await admin_category_cache_service.invalidate_all(redis_service=redis_service)
        await category_cache_service.invalidate_all(redis_service=redis_service)

        return AdminCategoryDetailResponse(
            id=category.id,
            name=category.name,
            slug=category.slug,
            description=category.description,
            parent_id=category.parent_id,
            image_url=category.image_url,
            sort_order=category.sort_order,
            is_active=category.is_active,
            created_at=category.created_date,
        )
