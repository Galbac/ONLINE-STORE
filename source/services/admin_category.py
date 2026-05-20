from datetime import datetime

from source.config.settings import settings
from source.errors.category import (
    CategoryCycleError,
    CategoryHasActiveChildrenError,
    CategoryHasActiveProductsError,
    CategoryNotFoundError,
    CategorySlugAlreadyExistsError,
)
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.upload import UploadNotFoundError
from source.schemas.pydantic.admin_category import (
    AdminCategoryCreateRequest,
    AdminCategoryDetailResponse,
    AdminCategoryImageResponse,
    AdminCategoryListItemResponse,
    AdminCategoryListQueryParams,
    AdminCategoryListResponse,
    AdminCategorySeoResponse,
    AdminCategoryShortResponse,
    AdminCategoryUpdateRequest,
    MessageResponse,
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

    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:categories:update" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_delete_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:categories:delete" not in permission_service.get_user_permissions(role=user.role):
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

    async def get_category_detail(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        category_id: int,
        permission_service,
        category_repository,
        product_repository,
        upload_repository,
        admin_category_cache_service,
    ) -> AdminCategoryDetailResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_category = await admin_category_cache_service.get_detail(
            redis_service=redis_service,
            category_id=category_id,
        )
        if cached_category is not None:
            return cached_category

        category = await category_repository.admin_get_by_id(session=session, category_id=category_id)
        if category is None:
            raise CategoryNotFoundError

        parent = None
        if category.parent_id is not None:
            parent_category = await category_repository.get_by_id(session=session, category_id=category.parent_id)
            if parent_category is not None:
                parent = self._build_short_response(category=parent_category)

        children = [
            self._build_short_response(category=child)
            for child in await category_repository.get_children(session=session, parent_id=category.id)
        ]
        image = None
        if category.image_file_id is not None:
            upload = await upload_repository.get_by_id(session=session, file_id=category.image_file_id)
            if upload is not None and not upload.is_deleted:
                image = AdminCategoryImageResponse(id=upload.id, url=upload.url)

        seo = None
        if category.meta_title is not None or category.meta_description is not None:
            seo = AdminCategorySeoResponse(
                meta_title=category.meta_title,
                meta_description=category.meta_description,
            )

        response = AdminCategoryDetailResponse(
            id=category.id,
            name=category.name,
            slug=category.slug,
            description=category.description,
            parent_id=category.parent_id,
            parent=parent,
            children=children,
            image=image,
            sort_order=category.sort_order,
            is_active=category.is_active,
            products_count=await product_repository.count_by_category_id(
                session=session,
                category_id=category.id,
            ),
            seo=seo,
        )
        await admin_category_cache_service.set_detail(
            redis_service=redis_service,
            category_id=category.id,
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

    def _build_short_response(self, *, category) -> AdminCategoryShortResponse:
        return AdminCategoryShortResponse(
            id=category.id,
            name=category.name,
            slug=category.slug,
        )

    async def update_category(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        category_id: int,
        data: AdminCategoryUpdateRequest,
        commiter,
        permission_service,
        category_repository,
        upload_repository,
        admin_audit_log_repository,
        audit_log_service,
        category_tree_service,
        category_cache_service,
        admin_category_cache_service,
        product_cache_service,
    ) -> AdminCategoryDetailResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise ValueError("No fields to update")

        category = await category_repository.admin_get_by_id(session=session, category_id=category_id)
        if category is None:
            raise CategoryNotFoundError
        old_slug = category.slug

        if "slug" in update_fields and update_fields["slug"] is not None:
            update_fields["slug"] = normalize_slug(update_fields["slug"])
            if not validate_slug(update_fields["slug"]):
                raise ValueError("Invalid slug")
            if update_fields["slug"] != category.slug:
                existing_category = await category_repository.get_by_slug(session=session, slug=update_fields["slug"])
                if existing_category is not None and existing_category.id != category.id:
                    raise CategorySlugAlreadyExistsError

        if "parent_id" in update_fields and update_fields["parent_id"] is not None:
            parent_id = update_fields["parent_id"]
            parent = await category_repository.get_by_id(session=session, category_id=parent_id)
            if parent is None:
                raise CategoryNotFoundError
            await category_tree_service.validate_no_cycle(
                session=session,
                category_repository=category_repository,
                category_id=category.id,
                parent_id=parent_id,
            )

        if "image_id" in update_fields:
            image_url = None
            if update_fields["image_id"] is not None:
                image = await upload_repository.get_by_id(session=session, file_id=update_fields["image_id"])
                if image is None or image.is_deleted:
                    raise UploadNotFoundError
                image_url = image.url
            update_fields["image_file_id"] = update_fields.pop("image_id")
            update_fields["image_url"] = image_url

        before = {
            field: getattr(category, field)
            for field in update_fields
        }
        updated_category = await category_repository.update(
            session=session,
            category=category,
            data=update_fields,
        )
        changes = {
            field: {
                "old": str(before[field]) if before[field] is not None else None,
                "new": str(getattr(updated_category, field)) if getattr(updated_category, field) is not None else None,
            }
            for field in update_fields
            if before[field] != getattr(updated_category, field)
        }
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_category_update",
            status="success",
            details={
                "category_id": updated_category.id,
                "changes": changes,
            },
        )
        await commiter.commit()

        await admin_category_cache_service.invalidate_all(redis_service=redis_service)
        await category_cache_service.invalidate_category(
            redis_service=redis_service,
            category_id=updated_category.id,
            slug=old_slug,
        )
        if updated_category.slug != old_slug:
            await category_cache_service.invalidate_category(
                redis_service=redis_service,
                category_id=updated_category.id,
                slug=updated_category.slug,
            )
        await product_cache_service.invalidate_all(redis_service=redis_service)

        return AdminCategoryDetailResponse(
            id=updated_category.id,
            name=updated_category.name,
            slug=updated_category.slug,
            parent_id=updated_category.parent_id,
            sort_order=updated_category.sort_order,
            is_active=updated_category.is_active,
            updated_at=updated_category.updated_date,
        )

    async def delete_category(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        category_id: int,
        commiter,
        permission_service,
        category_repository,
        product_repository,
        admin_audit_log_repository,
        audit_log_service,
        category_cache_service,
        admin_category_cache_service,
        product_cache_service,
    ) -> MessageResponse:
        self._check_delete_permission(user=user, permission_service=permission_service)

        category = await category_repository.admin_get_by_id(session=session, category_id=category_id)
        if category is None:
            raise CategoryNotFoundError
        if await category_repository.has_active_children(session=session, parent_id=category.id):
            raise CategoryHasActiveChildrenError
        if await product_repository.exists_by_category_id(session=session, category_id=category.id):
            raise CategoryHasActiveProductsError

        deleted_category = await category_repository.soft_delete(
            session=session,
            category=category,
            deleted_at=datetime.now(settings.tz),
            deleted_by=user.id,
        )
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_category_delete",
            status="success",
            details={
                "category_id": deleted_category.id,
                "name": deleted_category.name,
                "slug": deleted_category.slug,
            },
        )
        await commiter.commit()

        await admin_category_cache_service.invalidate_all(redis_service=redis_service)
        await category_cache_service.invalidate_category(
            redis_service=redis_service,
            category_id=deleted_category.id,
            slug=deleted_category.slug,
        )
        await product_cache_service.invalidate_all(redis_service=redis_service)

        return MessageResponse(message="Категория удалена")


class CategoryTreeService:
    async def validate_no_cycle(
        self,
        *,
        session,
        category_repository,
        category_id: int,
        parent_id: int,
    ) -> None:
        if parent_id == category_id:
            raise CategoryCycleError
        descendant_ids = await category_repository.get_descendant_ids(
            session=session,
            category_id=category_id,
        )
        if parent_id in descendant_ids:
            raise CategoryCycleError
