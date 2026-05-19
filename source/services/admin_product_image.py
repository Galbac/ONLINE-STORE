from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from datetime import datetime

from source.config.settings import settings
from source.errors.product import ProductImageNotFoundError, ProductImageOwnershipError, ProductNotFoundError
from source.schemas.pydantic.admin_product import AdminProductImageResponse, MessageResponse
from source.services.admin_auth import STAFF_ROLES


class AdminProductImageService:
    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:products:update" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def add_image(
        self,
        *,
        session,
        redis_service,
        user,
        product_id: int,
        file,
        sort_order: int,
        is_main: bool,
        commiter,
        media_settings,
        permission_service,
        product_repository,
        upload_service,
        storage_service,
        upload_repository,
        product_image_repository,
        admin_audit_log_repository,
        product_cache_service,
        admin_product_cache_service,
    ) -> AdminProductImageResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        row = await product_repository.admin_get_by_id(session=session, product_id=product_id)
        if row is None:
            raise ProductNotFoundError
        product, _category = row

        upload = await upload_service.upload_image(
            session=session,
            media_settings=media_settings,
            storage_service=storage_service,
            upload_repository=upload_repository,
            user=user,
            file=file,
            entity_type="product",
        )
        images_count = await product_image_repository.count_by_product_id(session=session, product_id=product.id)
        should_be_main = is_main or images_count == 0
        if should_be_main:
            await product_image_repository.unset_main_by_product_id(session=session, product_id=product.id)

        image = await product_image_repository.create(
            session=session,
            product_id=product.id,
            file_id=upload.id,
            url=upload.url,
            sort_order=sort_order,
            is_main=should_be_main,
        )
        await admin_audit_log_repository.create(
            session=session,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_product_image_add",
            status="success",
            details={
                "product_id": product.id,
                "image_id": image.id,
                "file_id": upload.id,
                "is_main": image.is_main,
            },
        )
        await commiter.commit()

        await product_cache_service.invalidate_product(
            redis_service=redis_service,
            product_id=product.id,
            slug=product.slug,
        )
        await admin_product_cache_service.invalidate_product(
            redis_service=redis_service,
            product_id=product.id,
        )

        return AdminProductImageResponse(
            id=image.id,
            product_id=image.product_id,
            file_id=image.file_id,
            url=image.url,
            sort_order=image.sort_order,
            is_main=image.is_main,
            created_at=image.created_date,
        )

    async def delete_image(
        self,
        *,
        session,
        redis_service,
        user,
        product_id: int,
        image_id: int,
        commiter,
        permission_service,
        product_repository,
        product_image_repository,
        admin_audit_log_repository,
        product_cache_service,
        admin_product_cache_service,
    ) -> MessageResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        row = await product_repository.admin_get_by_id(session=session, product_id=product_id)
        if row is None:
            raise ProductNotFoundError
        product, _category = row

        image = await product_image_repository.get_by_id(session=session, image_id=image_id)
        if image is None:
            raise ProductImageNotFoundError
        if image.product_id != product.id:
            raise ProductImageOwnershipError

        was_main = image.is_main
        deleted_image = await product_image_repository.soft_delete(
            session=session,
            image=image,
            deleted_at=datetime.now(settings.tz),
        )
        new_main_image_id = None
        if was_main:
            next_image = await product_image_repository.get_first_active_by_product_id(
                session=session,
                product_id=product.id,
            )
            if next_image is not None:
                next_image = await product_image_repository.set_main(session=session, image=next_image)
                new_main_image_id = next_image.id

        await admin_audit_log_repository.create(
            session=session,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_product_image_delete",
            status="success",
            details={
                "product_id": product.id,
                "image_id": deleted_image.id,
                "file_id": deleted_image.file_id,
                "was_main": was_main,
                "new_main_image_id": new_main_image_id,
            },
        )
        await commiter.commit()

        await product_cache_service.invalidate_product(
            redis_service=redis_service,
            product_id=product.id,
            slug=product.slug,
        )
        await admin_product_cache_service.invalidate_product(
            redis_service=redis_service,
            product_id=product.id,
        )

        return MessageResponse(message="Изображение товара удалено")
