from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from source.db.models.legal_document import LegalDocument
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.errors.legal_document import EmptyLegalDocumentUpdateError, LegalDocumentNotFoundError
from source.schemas.pydantic.legal_document import AdminLegalDocumentUpdateRequest
from source.services.legal_document import LegalDocumentService
from source.db.models.choises.enum import UserRole


@pytest.fixture
def service():
    return LegalDocumentService()


@pytest.fixture
def sample_doc():
    return LegalDocument(
        id=1,
        slug="offer",
        title="Публичная оферта",
        description="Описание оферты",
        content_html="<h2>1. Предмет</h2><p>Текст оферты</p>",
        is_active=True,
        created_date=datetime.now(timezone.utc),
        updated_date=datetime.now(timezone.utc),
    )


@pytest.fixture
def admin_user():
    user = MagicMock()
    user.id = 1
    user.is_active = True
    user.is_deleted = False
    user.is_blocked = False
    user.role = UserRole.ADMIN
    return user


@pytest.fixture
def permission_service():
    ps = MagicMock()
    ps.get_user_permissions.return_value = {"admin:settings:read", "admin:settings:update"}
    return ps


@pytest.mark.asyncio
async def test_get_public_document_success(service, sample_doc):
    session = AsyncMock()
    repo = AsyncMock()
    repo.get_active_by_slug.return_value = sample_doc

    result = await service.get_public_document(session=session, slug="offer", repository=repo)

    assert result.slug == "offer"
    assert result.title == "Публичная оферта"
    assert "<h2>1. Предмет</h2>" in result.content_html
    repo.get_active_by_slug.assert_called_once_with(session=session, slug="offer")


@pytest.mark.asyncio
async def test_get_public_document_not_found(service):
    session = AsyncMock()
    repo = AsyncMock()
    repo.get_active_by_slug.return_value = None

    with pytest.raises(LegalDocumentNotFoundError):
        await service.get_public_document(session=session, slug="nonexistent", repository=repo)


@pytest.mark.asyncio
async def test_get_admin_documents_success(service, sample_doc, admin_user, permission_service):
    session = AsyncMock()
    repo = AsyncMock()
    repo.get_all.return_value = [sample_doc]

    results = await service.get_admin_documents(
        session=session,
        user=admin_user,
        permission_service=permission_service,
        repository=repo,
    )

    assert len(results) == 1
    assert results[0].slug == "offer"


@pytest.mark.asyncio
async def test_get_admin_documents_permission_denied(service, sample_doc, admin_user):
    session = AsyncMock()
    repo = AsyncMock()
    ps = MagicMock()
    ps.get_user_permissions.return_value = set()

    with pytest.raises(AdminAuthAccessDeniedError):
        await service.get_admin_documents(
            session=session,
            user=admin_user,
            permission_service=ps,
            repository=repo,
        )


@pytest.mark.asyncio
async def test_update_admin_document_success(service, sample_doc, admin_user, permission_service):
    session = AsyncMock()
    repo = AsyncMock()
    commiter = AsyncMock()
    audit_log_service = AsyncMock()

    repo.get_by_slug.return_value = sample_doc

    updated_doc = LegalDocument(
        id=1,
        slug="offer",
        title="Новая Публичная Оферта",
        description="Обновленное описание",
        content_html="<h2>Обновленный заголовок</h2><p>Новый текст</p>",
        is_active=True,
        created_date=sample_doc.created_date,
        updated_date=datetime.now(timezone.utc),
    )
    repo.update.return_value = updated_doc

    update_req = AdminLegalDocumentUpdateRequest(
        title="Новая Публичная Оферта",
        content_html="<h2>Обновленный заголовок</h2><p>Новый текст</p>",
    )

    res = await service.update_admin_document(
        session=session,
        slug="offer",
        data=update_req,
        user=admin_user,
        permission_service=permission_service,
        repository=repo,
        commiter=commiter,
        audit_log_service=audit_log_service,
    )

    assert res.title == "Новая Публичная Оферта"
    assert res.content_html == "<h2>Обновленный заголовок</h2><p>Новый текст</p>"
    commiter.commit.assert_called_once()
    audit_log_service.log_action.assert_called_once()


@pytest.mark.asyncio
async def test_update_admin_document_empty_error(service, sample_doc, admin_user, permission_service):
    session = AsyncMock()
    repo = AsyncMock()
    commiter = AsyncMock()
    repo.get_by_slug.return_value = sample_doc

    empty_req = AdminLegalDocumentUpdateRequest()

    with pytest.raises(EmptyLegalDocumentUpdateError):
        await service.update_admin_document(
            session=session,
            slug="offer",
            data=empty_req,
            user=admin_user,
            permission_service=permission_service,
            repository=repo,
            commiter=commiter,
        )
