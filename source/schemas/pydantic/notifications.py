from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator


class NotificationQueryParams(BaseModel):
    unread_only: bool = False
    type: str | None = Field(default=None, max_length=50)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = value.strip()
        return normalized_value or None

    @computed_field
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    message: str
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    limit: int
    pages: int


class AdminNotificationSettingsResponse(BaseModel):
    email_enabled: bool
    email_from: EmailStr | None = None
    email_sender_name: str
    telegram_enabled: bool
    telegram_admin_chat_id: str | None = None
    notify_admin_new_order: bool
    notify_admin_payment_error: bool
    notify_admin_1c_error: bool
    notify_customer_order_created: bool
    notify_customer_order_status: bool
    notify_customer_payment: bool
    notify_customer_delivery: bool
    updated_at: datetime


class TestEmailRequest(BaseModel):
    __test__: ClassVar[bool] = False

    email: EmailStr
    subject: str | None = Field(default=None, max_length=255)
    message: str | None = Field(default=None, max_length=1000)

    @field_validator("subject", "message", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class TestTelegramRequest(BaseModel):
    __test__: ClassVar[bool] = False

    chat_id: str | None = Field(default=None, max_length=100)
    message: str | None = Field(default=None, max_length=1000)

    @field_validator("chat_id", "message", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class MessageResponse(BaseModel):
    message: str
    email: EmailStr | None = None
    chat_id: str | None = None
