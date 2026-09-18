from pydantic import BaseModel, EmailStr, Field


class StockAlertSubscribeRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)


class StockAlertSubscribeResponse(BaseModel):
    message: str
    product_id: int
    is_subscribed: bool = True
