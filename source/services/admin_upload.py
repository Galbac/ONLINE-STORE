from datetime import datetime

from fastapi import UploadFile

from source.config.settings import MediaSettings, settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.upload import UploadInUseError, UploadNotFoundError
from source.schemas.pydantic.upload import AdminUploadImageResponse
from source.services.admin_auth import STAFF_ROLES
from source.services.storage import StorageService
from source.utils.upload import generate_safe_filename, get_file_extension, validate_image_file


class AdminUploadService:
    def _check_create_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:uploads:create" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_delete_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:uploads:delete" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def upload_image(
        self,
        *,
        session,
        user,
        file: UploadFile | None,
        entity_type: str | None,
        media_settings: MediaSettings,
        storage_service: StorageService,
        upload_repository,
        permission_service,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUploadImageResponse:
        self._check_create_permission(user=user, permission_service=permission_service)

        content = await validate_image_file(
            file=file,
            allowed_mime_types=media_settings.allowed_image_type_set,
            allowed_extensions=media_settings.allowed_image_extension_set,
            max_size_bytes=media_settings.max_image_size_mb * 1024 * 1024,
        )
        extension = get_file_extension(file.filename if file is not None else None)
        stored_filename = generate_safe_filename(extension=extension, entity_type=entity_type)
        url, storage_type = await storage_service.save_file(stored_filename=stored_filename, content=content)

        upload = await upload_repository.create(
            session=session,
            original_filename=file.filename,
            stored_filename=stored_filename,
            mime_type=file.content_type,
            size=len(content),
            storage_type=storage_type,
            url=url,
            entity_type=entity_type,
            uploaded_by=user.id,
        )
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_upload_image_create",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "file_id": upload.id,
                "original_filename": upload.original_filename,
                "stored_filename": upload.stored_filename,
                "mime_type": upload.mime_type,
                "size": upload.size,
                "storage_type": upload.storage_type,
                "entity_type": upload.entity_type,
            },
        )
        return self._build_response(upload)

    async def delete_file(
        self,
        *,
        session,
        redis_service,
        user,
        file_id: int,
        storage_service: StorageService,
        permission_service,
        upload_repository,
        product_image_repository,
        category_repository,
        upload_cache_service,
        audit_log_service,
        admin_audit_log_repository,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._check_delete_permission(user=user, permission_service=permission_service)

        upload = await upload_repository.get_by_id(session=session, file_id=file_id)
        if upload is None or upload.is_deleted:
            raise UploadNotFoundError

        if await product_image_repository.exists_by_file_id(session=session, file_id=file_id):
            raise UploadInUseError
        if await category_repository.exists_by_image_file_id(session=session, file_id=file_id):
            raise UploadInUseError

        await storage_service.delete_file(storage_type=upload.storage_type, stored_filename=upload.stored_filename)
        await upload_repository.soft_delete(
            session=session,
            upload=upload,
            deleted_by=user.id,
            deleted_at=datetime.now(settings.tz),
        )
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_upload_file_delete",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "file_id": upload.id,
                "stored_filename": upload.stored_filename,
                "storage_type": upload.storage_type,
                "entity_type": upload.entity_type,
            },
        )
        await upload_cache_service.invalidate_detail(redis_service=redis_service, file_id=file_id)

    def _build_response(self, upload) -> AdminUploadImageResponse:
        return AdminUploadImageResponse(
            id=upload.id,
            url=upload.url,
            original_filename=upload.original_filename,
            stored_filename=upload.stored_filename,
            mime_type=upload.mime_type,
            size=upload.size,
            storage_type=upload.storage_type,
            entity_type=upload.entity_type,
            created_at=upload.created_date,
        )
