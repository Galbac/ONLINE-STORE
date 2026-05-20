from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator

from source.db.models.choises.enum import UserRole


class AdminStaffListQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None
    is_blocked: bool | None = None

    @field_validator("q", mode="before")
    @classmethod
    def normalize_q(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None

    @computed_field
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class AdminStaffListItemResponse(BaseModel):
    id: int
    name: str
    email: EmailStr | None
    phone: str
    role: UserRole
    is_active: bool
    is_blocked: bool
    created_at: datetime


class AdminStaffListResponse(BaseModel):
    items: list[AdminStaffListItemResponse]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminStaffListItemResponse],
        total: int,
        page: int,
        limit: int,
    ) -> "AdminStaffListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit if total else 0,
        )
