import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from pydantic import TypeAdapter

from source.db.models.choises.enum import UserRole


class UserRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=5, max_length=32)
    email: EmailStr | None = None
    password: str = Field(min_length=8)


class UserLoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class ForgotPasswordRequest(BaseModel):
    login: str = Field(min_length=3, max_length=255)

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


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
    new_password_confirm: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        has_upper = any(char.isupper() for char in value)
        has_lower = any(char.islower() for char in value)
        has_digit = any(char.isdigit() for char in value)
        if not (has_upper and has_lower and has_digit):
            raise ValueError("Пароль слишком слабый")
        return value

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.new_password_confirm:
            raise ValueError("Пароли не совпадают")
        return self


class MessageResponse(BaseModel):
    message: str


class UserShortResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr | None
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UserResponse(UserShortResponse):
    pass


class RegisterAuthResponse(UserShortResponse):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    user: UserShortResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
