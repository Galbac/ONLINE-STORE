from datetime import datetime
from pydantic import BaseModel, ConfigDict


class LoyaltyTransactionResponse(BaseModel):
    id: int
    amount: int
    transaction_type: str
    description: str
    order_id: int | None = None
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


class LoyaltyResponse(BaseModel):
    balance: int
    level: str = "Базовый"
    cashback_percent: int = 5
    transactions: list[LoyaltyTransactionResponse]
