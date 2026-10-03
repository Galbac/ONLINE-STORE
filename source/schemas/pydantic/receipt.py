from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class ReceiptItemResponse(BaseModel):
    name: str
    quantity: Decimal
    price: Decimal
    total_amount: Decimal
    payment_subject: int = 1  # 1 - ТОВАР, 4 - УСЛУГА
    payment_subject_name: str = "ТОВАР"

    model_config = ConfigDict(from_attributes=True)


class OrderReceiptResponse(BaseModel):
    order_id: int
    order_number: str
    available: bool
    message: str
    receipt_url: str | None = None
    fiscal_number: str | None = None
    total_amount: Decimal | None = None
    issued_at: datetime | None = None
    items: list[ReceiptItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
