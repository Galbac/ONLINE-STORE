from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class OrderReceiptResponse(BaseModel):
    order_id: int
    order_number: str
    receipt_url: str
    fiscal_number: str
    total_amount: Decimal
    issued_at: datetime

    model_config = ConfigDict(from_attributes=True)
