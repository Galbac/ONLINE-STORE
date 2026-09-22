from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.legal_document import LegalDocument


class LegalDocumentRepository:
    async def get_by_slug(self, *, session: AsyncSession, slug: str) -> LegalDocument | None:
        stmt = select(LegalDocument).where(LegalDocument.slug == slug)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_slug(self, *, session: AsyncSession, slug: str) -> LegalDocument | None:
        stmt = select(LegalDocument).where(LegalDocument.slug == slug, LegalDocument.is_active.is_(True))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, *, session: AsyncSession) -> list[LegalDocument]:
        stmt = select(LegalDocument).order_by(LegalDocument.id.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, *, session: AsyncSession, **kwargs) -> LegalDocument:
        document = LegalDocument(**kwargs)
        session.add(document)
        await session.flush()
        await session.refresh(document)
        return document

    async def update(self, *, session: AsyncSession, document: LegalDocument, **kwargs) -> LegalDocument:
        for key, value in kwargs.items():
            setattr(document, key, value)
        session.add(document)
        await session.flush()
        await session.refresh(document)
        return document
