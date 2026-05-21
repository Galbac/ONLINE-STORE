from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.upload import Upload


class UploadRepository:
    async def create(
        self,
        *,
        session: AsyncSession,
        original_filename: str,
        stored_filename: str,
        mime_type: str,
        size: int,
        storage_type: str,
        url: str,
        entity_type: str | None,
        uploaded_by: int | None,
    ) -> Upload:
        upload = Upload(
            original_filename=original_filename,
            stored_filename=stored_filename,
            mime_type=mime_type,
            size=size,
            storage_type=storage_type,
            url=url,
            entity_type=entity_type,
            uploaded_by=uploaded_by,
        )
        session.add(upload)
        await session.flush()
        return upload

    async def get_by_id(self, *, session: AsyncSession, file_id: int) -> Upload | None:
        result = await session.execute(select(Upload).where(Upload.id == file_id))
        return result.scalar_one_or_none()

    async def soft_delete(
        self,
        *,
        session: AsyncSession,
        upload: Upload,
        deleted_by: int,
        deleted_at: datetime,
    ) -> Upload:
        upload.is_deleted = True
        upload.deleted_by = deleted_by
        upload.deleted_at = deleted_at
        session.add(upload)
        await session.flush()
        return upload
