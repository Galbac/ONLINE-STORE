from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.errors.legal_document import LegalDocumentNotFoundError
from source.repositories.legal_document import LegalDocumentRepository
from source.schemas.pydantic.legal_document import LegalDocumentResponse
from source.services.legal_document import LegalDocumentService

router = APIRouter(prefix="/legal-documents", tags=["legal-documents"])


@router.get("/{slug}", response_model=LegalDocumentResponse, status_code=status.HTTP_200_OK)
@inject
async def get_legal_document(
    slug: str,
    session: FromDishka[AsyncSession] = None,
    legal_document_repository: FromDishka[LegalDocumentRepository] = None,
    legal_document_service: FromDishka[LegalDocumentService] = None,
) -> LegalDocumentResponse:
    try:
        return await legal_document_service.get_public_document(
            session=session,
            slug=slug,
            repository=legal_document_repository,
        )
    except LegalDocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Юридический документ '{slug}' не найден",
        )
