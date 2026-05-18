from typing import Literal

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, require_admin_or_manager, resolve_access_token, resolve_current_user_by_payload
from source.common.commiter import Commiter
from source.config.settings import Settings
from source.db.models.user import User
from source.errors.upload import (
    UploadAccessDeniedError,
    UploadFileMissingError,
    UploadFileTooLargeError,
    UploadInUseError,
    UploadNotFoundError,
    UploadPrivateAccessRequiredError,
    UploadStorageError,
    UploadUnsupportedFormatError,
)
from source.repositories.category import CategoryRepository
from source.repositories.product_image import ProductImageRepository
from source.repositories.upload import UploadRepository
from source.schemas.pydantic.auth import MessageResponse
from source.schemas.pydantic.upload import UploadFileResponse, UploadImageResponse
from source.services.redis import RedisService
from source.services.storage import StorageService
from source.services.upload import UploadService
from source.services.upload_cache import UploadCacheService

router = APIRouter(tags=["uploads"])


@router.post("/uploads/image", response_model=UploadImageResponse, status_code=status.HTTP_201_CREATED)
@inject
async def upload_image(
    file: UploadFile | None = File(default=None),
    entity_type: Literal["product", "category", "banner", "other"] | None = Form(default=None),
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    config: FromDishka[Settings] = None,
    storage_service: FromDishka[StorageService] = None,
    upload_service: FromDishka[UploadService] = None,
    upload_repository: FromDishka[UploadRepository] = None,
) -> UploadImageResponse:
    try:
        response = await upload_service.upload_image(
            session=session,
            media_settings=config.media,
            storage_service=storage_service,
            upload_repository=upload_repository,
            user=current_user,
            file=file,
            entity_type=entity_type,
        )
        await commiter.commit()
        return response
    except UploadFileMissingError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не передан") from error
    except UploadUnsupportedFormatError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неподдерживаемый формат файла") from error
    except UploadFileTooLargeError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой") from error
    except UploadStorageError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка сохранения файла") from error


@router.delete("/uploads/{file_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@inject
async def delete_upload(
    file_id: int,
    current_user: User = Depends(require_admin_or_manager),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    storage_service: FromDishka[StorageService] = None,
    upload_service: FromDishka[UploadService] = None,
    upload_cache_service: FromDishka[UploadCacheService] = None,
    upload_repository: FromDishka[UploadRepository] = None,
    product_image_repository: FromDishka[ProductImageRepository] = None,
    category_repository: FromDishka[CategoryRepository] = None,
) -> MessageResponse:
    if file_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный file_id")
    try:
        await upload_service.delete_file(
            session=session,
            redis_service=redis_service,
            storage_service=storage_service,
            upload_cache_service=upload_cache_service,
            upload_repository=upload_repository,
            product_image_repository=product_image_repository,
            category_repository=category_repository,
            user=current_user,
            file_id=file_id,
        )
        await commiter.commit()
        return MessageResponse(message="Файл успешно удалён")
    except UploadNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден") from error
    except UploadInUseError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Файл используется и не может быть удалён") from error
    except UploadStorageError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка удаления файла") from error


@router.get("/uploads/{file_id}", response_model=UploadFileResponse, status_code=status.HTTP_200_OK)
@inject
async def get_upload_detail(
    file_id: int,
    authorization: str | None = Header(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    upload_service: FromDishka[UploadService] = None,
    upload_cache_service: FromDishka[UploadCacheService] = None,
    upload_repository: FromDishka[UploadRepository] = None,
) -> UploadFileResponse:
    if file_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный file_id")

    user = None
    if authorization is not None:
        payload = await resolve_access_token(authorization=authorization, redis_service=redis_service)
        user = await resolve_current_user_by_payload(token_payload=payload, session=session)
    try:
        return await upload_service.get_file_detail(
            session=session,
            redis_service=redis_service,
            upload_cache_service=upload_cache_service,
            upload_repository=upload_repository,
            file_id=file_id,
            user=user,
        )
    except UploadNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден") from error
    except UploadPrivateAccessRequiredError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация") from error
    except UploadAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа") from error
