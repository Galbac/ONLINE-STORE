from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ReviewResponse(BaseModel):
    id: int
    product_id: int
    user_id: int
    user_name: str
    rating: int
    text: str
    pros: str | None = None
    cons: str | None = None
    image_url: str | None = None
    is_approved: bool = True
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewCreateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=3, max_length=2000)
    pros: str | None = Field(default=None, max_length=500)
    cons: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=1000)


class ReviewModerateRequest(BaseModel):
    is_approved: bool


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    average_rating: float = 5.0
