from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class BannerResponse(BaseModel):
    id: int
    title: str
    subtitle: str | None = None
    badge: str | None = None
    image_url: str | None = None
    link: str | None = None
    bg_color: str = "#059669"
    sort_order: int = 0
    is_active: bool = True
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


class BannerCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=255)
    badge: str | None = Field(default=None, max_length=100)
    image_url: str | None = Field(default=None, max_length=500)
    link: str | None = Field(default=None, max_length=500)
    bg_color: str = Field(default="#059669", max_length=50)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class BannerUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=255)
    badge: str | None = Field(default=None, max_length=100)
    image_url: str | None = Field(default=None, max_length=500)
    link: str | None = Field(default=None, max_length=500)
    bg_color: str | None = Field(default=None, max_length=50)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class BannerListResponse(BaseModel):
    items: list[BannerResponse]
    total: int
