from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr

from source.db.models.choises.enum import UserRole


class ProfileUserResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr | None
    role: UserRole
    is_active: bool
    is_verified: bool = False


class ProfileStatsResponse(BaseModel):
    orders_count: int
    addresses_count: int


class ProfileAddressShortResponse(BaseModel):
    id: int
    city: str
    street: str
    house: str
    apartment: str | None = None


class ProfileOrderShortResponse(BaseModel):
    id: int
    order_number: str
    status: str
    final_price: Decimal
    created_at: datetime


class ProfileSummaryResponse(BaseModel):
    user: ProfileUserResponse
    stats: ProfileStatsResponse
    default_address: ProfileAddressShortResponse | None = None
    active_order: ProfileOrderShortResponse | None = None
    recent_orders: list[ProfileOrderShortResponse]
