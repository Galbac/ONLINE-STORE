from datetime import datetime

from pydantic import BaseModel


class UploadFileResponse(BaseModel):
    id: int
    url: str
    original_filename: str
    mime_type: str
    size: int
    storage_type: str
    entity_type: str | None = None
    created_at: datetime


class UploadImageResponse(UploadFileResponse):
    pass


class AdminUploadImageResponse(UploadFileResponse):
    stored_filename: str
