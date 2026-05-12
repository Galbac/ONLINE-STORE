from pydantic import BaseModel, ConfigDict, EmailStr, Field

from source.db.models.choises.enum import UserRole


class UserRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=5, max_length=32)
    email: EmailStr | None = None
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr | None
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(UserResponse):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
