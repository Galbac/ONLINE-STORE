from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

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


class AddressListQueryParams(BaseModel):
    include_deleted: bool = False
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class AddressResponse(BaseModel):
    id: int
    title: str | None = None
    city: str
    street: str
    house: str
    building: str | None = None
    apartment: str | None = None
    entrance: str | None = None
    floor: str | None = None
    intercom: str | None = None
    comment: str | None = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class AddressListResponse(BaseModel):
    items: list[AddressResponse]
    total: int
    limit: int
    offset: int


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
