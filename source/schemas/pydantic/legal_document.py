from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LegalDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    description: str | None = None
    content_html: str
    is_active: bool
    updated_date: datetime | None = None


class AdminLegalDocumentListItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    description: str | None = None
    is_active: bool
    updated_date: datetime | None = None


class AdminLegalDocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    content_html: str | None = None
    is_active: bool | None = None
