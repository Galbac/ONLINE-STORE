from sqlalchemy.ext.asyncio import AsyncSession

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
from source.services.admin_auth import AuditLogService, PermissionService, STAFF_ROLES


class LegalDocumentService:
    def _check_read_permission(self, *, user: User, permission_service: PermissionService) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:settings:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_update_permission(self, *, user: User, permission_service: PermissionService) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:settings:update" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_public_document(
        self,
        *,
        session: AsyncSession,
        slug: str,
        repository: LegalDocumentRepository,
    ) -> LegalDocumentResponse:
        doc = await repository.get_active_by_slug(session=session, slug=slug)
        if not doc:
            raise LegalDocumentNotFoundError
        return LegalDocumentResponse.model_validate(doc)

    async def get_admin_documents(
        self,
        *,
        session: AsyncSession,
        user: User,
        permission_service: PermissionService,
        repository: LegalDocumentRepository,
    ) -> list[AdminLegalDocumentListItemResponse]:
        self._check_read_permission(user=user, permission_service=permission_service)
        docs = await repository.get_all(session=session)
        return [AdminLegalDocumentListItemResponse.model_validate(d) for d in docs]

    async def get_admin_document(
        self,
        *,
        session: AsyncSession,
        slug: str,
        user: User,
        permission_service: PermissionService,
        repository: LegalDocumentRepository,
    ) -> LegalDocumentResponse:
        self._check_read_permission(user=user, permission_service=permission_service)
        doc = await repository.get_by_slug(session=session, slug=slug)
        if not doc:
            raise LegalDocumentNotFoundError
        return LegalDocumentResponse.model_validate(doc)

    async def update_admin_document(
        self,
        *,
        session: AsyncSession,
        slug: str,
        data: AdminLegalDocumentUpdateRequest,
        user: User,
        permission_service: PermissionService,
        repository: LegalDocumentRepository,
        commiter: Commiter,
        audit_log_service: AuditLogService | None = None,
    ) -> LegalDocumentResponse:
        self._check_update_permission(user=user, permission_service=permission_service)
        doc = await repository.get_by_slug(session=session, slug=slug)
        if not doc:
            raise LegalDocumentNotFoundError

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyLegalDocumentUpdateError

        before_state = {k: getattr(doc, k) for k in update_fields.keys()}
        updated_doc = await repository.update(session=session, document=doc, **update_fields)

        if audit_log_service is not None:
            await audit_log_service.log_action(
                session=session,
                user_id=user.id,
                action="admin.legal_document.update",
                entity_type="legal_document",
                entity_id=updated_doc.id,
                before=before_state,
                after=update_fields,
            )

        await commiter.commit()
        return LegalDocumentResponse.model_validate(updated_doc)
