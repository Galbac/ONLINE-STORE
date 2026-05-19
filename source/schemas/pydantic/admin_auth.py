import re

from pydantic import BaseModel, EmailStr, Field, TypeAdapter, field_validator

from source.db.models.choises.enum import UserRole


class AdminLoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)

    @field_validator("login")
    @classmethod
    def validate_login(cls, value: str) -> str:
        login = value.strip()
        if not login:
            raise ValueError("login is required")
        if "@" in login:
            TypeAdapter(EmailStr).validate_python(login)
            return login.lower()
        if re.fullmatch(r"\+?\d{5,15}", login) is None:
            raise ValueError("login must be a valid email or phone")
        return login


class AdminUserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr | None
    phone: str
    role: UserRole
    permissions: list[str]


class AdminAuthResponse(BaseModel):
    user: AdminUserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AdminLogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class MessageResponse(BaseModel):
    message: str
