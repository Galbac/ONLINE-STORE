from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


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
    receipt_url: str
    fiscal_number: str
    total_amount: Decimal
    issued_at: datetime
    items: list[ReceiptItemResponse] = []

    model_config = ConfigDict(from_attributes=True)
