from datetime import datetime

from pydantic import BaseModel, EmailStr

from source.db.models.choises.enum import UserRole


class UserMeResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr | None
    role: UserRole
    is_active: bool
    is_verified: bool = False
    created_at: datetime
    updated_at: datetime
