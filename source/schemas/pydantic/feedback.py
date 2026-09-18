from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    subject: str = Field(min_length=2, max_length=255)
    message: str = Field(min_length=5, max_length=3000)
    order_id: int | None = Field(default=None, ge=1)


class FeedbackResponse(BaseModel):
    id: int
    name: str
    email: str | None = None
    phone: str | None = None
    subject: str
    message: str
    order_id: int | None = None
    status: str = "new"
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int


class FeedbackStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(new|in_progress|resolved)$")


class FeedbackReplyRequest(BaseModel):
    message: str = Field(min_length=2, max_length=5000)
