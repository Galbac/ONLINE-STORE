from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import require_permission
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.legal_document import EmptyLegalDocumentUpdateError, LegalDocumentNotFoundError
from source.repositories.legal_document import LegalDocumentRepository
from source.schemas.pydantic.legal_document import (
    AdminLegalDocumentListItemResponse,
    AdminLegalDocumentUpdateRequest,
    LegalDocumentResponse,
)
from source.services.admin_auth import AuditLogService, PermissionService
from source.services.legal_document import LegalDocumentService

router = APIRouter(prefix="/admin/legal-documents", tags=["admin-legal-documents"])


@router.get("", response_model=list[AdminLegalDocumentListItemResponse], status_code=status.HTTP_200_OK)
@inject
async def list_admin_legal_documents(
    current_user: User = Depends(require_permission("admin:settings:read")),
    session: FromDishka[AsyncSession] = None,
    legal_document_repository: FromDishka[LegalDocumentRepository] = None,
    legal_document_service: FromDishka[LegalDocumentService] = None,
    permission_service: FromDishka[PermissionService] = None,
) -> list[AdminLegalDocumentListItemResponse]:
    try:
        return await legal_document_service.get_admin_documents(
            session=session,
            user=current_user,
            permission_service=permission_service,
            repository=legal_document_repository,
        )
    except (AdminAuthAccessDeniedError, InactiveUserError) as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен") from err


@router.get("/{slug}", response_model=LegalDocumentResponse, status_code=status.HTTP_200_OK)
@inject
async def get_admin_legal_document(
    slug: str,
    current_user: User = Depends(require_permission("admin:settings:read")),
    session: FromDishka[AsyncSession] = None,
    legal_document_repository: FromDishka[LegalDocumentRepository] = None,
    legal_document_service: FromDishka[LegalDocumentService] = None,
    permission_service: FromDishka[PermissionService] = None,
) -> LegalDocumentResponse:
    try:
        return await legal_document_service.get_admin_document(
            session=session,
            slug=slug,
            user=current_user,
            permission_service=permission_service,
            repository=legal_document_repository,
        )
    except (AdminAuthAccessDeniedError, InactiveUserError) as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен") from err
    except LegalDocumentNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Документ '{slug}' не найден") from err


@router.patch("/{slug}", response_model=LegalDocumentResponse, status_code=status.HTTP_200_OK)
@inject
async def update_admin_legal_document(
    slug: str,
    payload: AdminLegalDocumentUpdateRequest,
    current_user: User = Depends(require_permission("admin:settings:update")),
    session: FromDishka[AsyncSession] = None,
    legal_document_repository: FromDishka[LegalDocumentRepository] = None,
    legal_document_service: FromDishka[LegalDocumentService] = None,
    permission_service: FromDishka[PermissionService] = None,
    audit_log_service: FromDishka[AuditLogService] = None,
    commiter: FromDishka[Commiter] = None,
) -> LegalDocumentResponse:
    try:
        return await legal_document_service.update_admin_document(
            session=session,
            slug=slug,
            data=payload,
            user=current_user,
            permission_service=permission_service,
            repository=legal_document_repository,
            commiter=commiter,
            audit_log_service=audit_log_service,
        )
    except (AdminAuthAccessDeniedError, InactiveUserError) as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен") from err
    except LegalDocumentNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Документ '{slug}' не найден") from err
    except EmptyLegalDocumentUpdateError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нет данных для обновления") from err
