from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.admin_legal_documents import (
    get_admin_legal_document,
    list_admin_legal_documents,
    update_admin_legal_document,
)
from source.api.api_v1.views.legal_documents import get_legal_document
from source.errors.legal_document import EmptyLegalDocumentUpdateError, LegalDocumentNotFoundError
from source.schemas.pydantic.legal_document import (
    AdminLegalDocumentListItemResponse,
    AdminLegalDocumentUpdateRequest,
    LegalDocumentResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.mark.asyncio
async def test_public_get_legal_document_success():
    service = AsyncMock()
    repo = AsyncMock()
    session = AsyncMock()

    doc_response = LegalDocumentResponse(
        slug="offer",
        title="Публичная оферта",
        description="Описание",
        content_html="<h2>Текст оферты</h2>",
        is_active=True,
        updated_date=datetime.now(timezone.utc),
    )
    service.get_public_document.return_value = doc_response

    resp = await unwrap(get_legal_document)(
        slug="offer",
        session=session,
        legal_document_repository=repo,
        legal_document_service=service,
    )

    assert resp.slug == "offer"
    assert resp.title == "Публичная оферта"
    assert resp.content_html == "<h2>Текст оферты</h2>"


@pytest.mark.asyncio
async def test_public_get_legal_document_not_found():
    service = AsyncMock()
    repo = AsyncMock()
    session = AsyncMock()
    service.get_public_document.side_effect = LegalDocumentNotFoundError

    with pytest.raises(HTTPException) as exc_info:
        await unwrap(get_legal_document)(
            slug="unknown",
            session=session,
            legal_document_repository=repo,
            legal_document_service=service,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_list_legal_documents():
    service = AsyncMock()
    repo = AsyncMock()
    session = AsyncMock()
    user = AsyncMock()
    permission_service = AsyncMock()

    item = AdminLegalDocumentListItemResponse(
        slug="offer",
        title="Публичная оферта",
        is_active=True,
        updated_date=datetime.now(timezone.utc),
    )
    service.get_admin_documents.return_value = [item]

    res = await unwrap(list_admin_legal_documents)(
        current_user=user,
        session=session,
        legal_document_repository=repo,
        legal_document_service=service,
        permission_service=permission_service,
    )

    assert len(res) == 1
    assert res[0].slug == "offer"


@pytest.mark.asyncio
async def test_admin_update_legal_document_success():
    service = AsyncMock()
    repo = AsyncMock()
    session = AsyncMock()
    user = AsyncMock()
    permission_service = AsyncMock()
    commiter = AsyncMock()
    audit_log_service = AsyncMock()

    updated = LegalDocumentResponse(
        slug="offer",
        title="Обновленная оферта",
        content_html="<h2>Новый текст</h2>",
        is_active=True,
        updated_date=datetime.now(timezone.utc),
    )
    service.update_admin_document.return_value = updated

    payload = AdminLegalDocumentUpdateRequest(title="Обновленная оферта", content_html="<h2>Новый текст</h2>")

    res = await unwrap(update_admin_legal_document)(
        slug="offer",
        payload=payload,
        current_user=user,
        session=session,
        legal_document_repository=repo,
        legal_document_service=service,
        permission_service=permission_service,
        audit_log_service=audit_log_service,
        commiter=commiter,
    )

    assert res.title == "Обновленная оферта"
    assert res.content_html == "<h2>Новый текст</h2>"
