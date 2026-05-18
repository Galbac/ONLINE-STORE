from decimal import Decimal

from pydantic import BaseModel


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
