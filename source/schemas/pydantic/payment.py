from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    order_id: int = Field(gt=0)


class PaymentConfirmRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)


class PaymentCreateResponse(BaseModel):
    id: int
    order_id: int
    order_number: str
    amount: Decimal
    currency: str
    status: str
    provider: str
    payment_url: str
    created_at: datetime


class PaymentDetailResponse(BaseModel):
    id: int
    order_id: int
    order_number: str
    amount: Decimal
    currency: str
    status: str
    provider: str
    payment_url: str | None = None
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PaymentConfirmResponse(BaseModel):
    id: int
    order_id: int
    status: str
    amount: Decimal
    currency: str
    paid_at: datetime | None = None
