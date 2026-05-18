from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from source.utils.delivery import normalize_address_part


class DeliveryOptionItemResponse(BaseModel):
    enabled: bool
    title: str
    description: str
    min_order_amount: Decimal | None = None
    base_price: Decimal | None = None
    free_from_amount: Decimal | None = None
    has_time_slots: bool | None = None
    price: Decimal | None = None
    has_pickup_points: bool | None = None


class DeliveryOptionsResponse(BaseModel):
    delivery: DeliveryOptionItemResponse
    pickup: DeliveryOptionItemResponse


class DeliveryCalculateRequest(BaseModel):
    city: str | None = Field(default=None, min_length=1, max_length=100)
    street: str | None = Field(default=None, min_length=1, max_length=150)
    house: str | None = Field(default=None, min_length=1, max_length=50)
    apartment: str | None = Field(default=None, max_length=50)
    order_amount: Decimal = Field(gt=0)
    address_id: int | None = Field(default=None, gt=0)

    @field_validator("city", "street", "house", "apartment", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        return normalize_address_part(value)

    @model_validator(mode="after")
    def validate_address_fields(self) -> "DeliveryCalculateRequest":
        if self.address_id is None and (self.city is None or self.street is None or self.house is None):
            raise ValueError("city, street и house обязательны, если address_id не передан")
        return self


class DeliveryZoneShortResponse(BaseModel):
    id: int
    name: str


class DeliveryCalculateResponse(BaseModel):
    available: bool
    delivery_price: Decimal | None = None
    free_delivery_from: Decimal | None = None
    amount_left_for_free_delivery: Decimal | None = None
    min_order_amount: Decimal | None = None
    zone: DeliveryZoneShortResponse | None = None
    message: str


class PickupPointListQueryParams(BaseModel):
    city: str | None = Field(default=None, max_length=100)
    only_active: bool = True
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("city", mode="before")
    @classmethod
    def normalize_city(cls, value: str | None) -> str | None:
        return normalize_address_part(value)


class PickupPointResponse(BaseModel):
    id: int
    name: str
    city: str
    address: str
    working_hours: str | None = None
    phone: str | None = None
    is_active: bool
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class PickupPointDetailResponse(PickupPointResponse):
    description: str | None = None


class PickupPointListResponse(BaseModel):
    items: list[PickupPointResponse]
    total: int
    limit: int
    offset: int


class DeliveryTimeSlotsQueryParams(BaseModel):
    date: date
    delivery_type: str = Field(pattern="^(delivery|pickup)$")
    pickup_point_id: int | None = Field(default=None, gt=0)
    address_id: int | None = Field(default=None, gt=0)
    city: str | None = Field(default=None, max_length=100)

    @field_validator("city", mode="before")
    @classmethod
    def normalize_slot_city(cls, value: str | None) -> str | None:
        return normalize_address_part(value)


class DeliveryTimeSlotResponse(BaseModel):
    id: int
    start_time: str
    end_time: str
    label: str
    available: bool
    orders_limit: int | None = None
    orders_count: int | None = None
    reason: str | None = None


class DeliveryTimeSlotsResponse(BaseModel):
    date: date
    delivery_type: str
    items: list[DeliveryTimeSlotResponse]
