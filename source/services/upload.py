from datetime import datetime

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import MediaSettings, settings
from source.db.models.choises.enum import UserRole
from source.errors.upload import UploadAccessDeniedError, UploadInUseError, UploadNotFoundError, UploadPrivateAccessRequiredError
from source.repositories.category import CategoryRepository
from source.repositories.product_image import ProductImageRepository
from source.repositories.upload import UploadRepository
from source.schemas.pydantic.upload import UploadFileResponse, UploadImageResponse
from source.services.redis import RedisService
from source.services.storage import StorageService
from source.services.upload_cache import UploadCacheService
from source.utils.upload import generate_safe_filename, get_file_extension, validate_image_file


class UploadService:
    async def upload_image(
        self,
        *,
        session: AsyncSession,
        media_settings: MediaSettings,
        storage_service: StorageService,
        upload_repository: UploadRepository,
        user,
        file: UploadFile | None,
        entity_type: str | None,
    ) -> UploadImageResponse:
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
        return self._build_response(upload)

    async def delete_file(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        storage_service: StorageService,
        upload_cache_service: UploadCacheService,
        upload_repository: UploadRepository,
        product_image_repository: ProductImageRepository,
        category_repository: CategoryRepository,
        user,
        file_id: int,
    ) -> None:
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
        await upload_cache_service.invalidate_detail(redis_service=redis_service, file_id=file_id)

    async def get_file_detail(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        upload_cache_service: UploadCacheService,
        upload_repository: UploadRepository,
        file_id: int,
        user=None,
    ) -> UploadFileResponse:
        cached = await upload_cache_service.get_detail(redis_service=redis_service, file_id=file_id)
        if cached is not None:
            return cached

        upload = await upload_repository.get_by_id(session=session, file_id=file_id)
        if upload is None or upload.is_deleted:
            raise UploadNotFoundError
        if not upload.is_public and user is None:
            raise UploadPrivateAccessRequiredError
        if not upload.is_public and user.id != upload.uploaded_by and user.role not in {UserRole.ADMIN, UserRole.MANAGER}:
            raise UploadAccessDeniedError

        response = self._build_response(upload)
        if upload.is_public:
            await upload_cache_service.set_detail(
                redis_service=redis_service,
                file_id=file_id,
                response=response,
                ttl_seconds=settings.media.detail_cache_ttl_seconds,
            )
        return response

    def _build_response(self, upload) -> UploadImageResponse:
        return UploadImageResponse(
            id=upload.id,
            url=upload.url,
            original_filename=upload.original_filename,
            mime_type=upload.mime_type,
            size=upload.size,
            storage_type=upload.storage_type,
            entity_type=upload.entity_type,
            created_at=upload.created_date,
        )
