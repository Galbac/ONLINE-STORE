from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OrderTrackingStep(BaseModel):
    step_key: str
    title: str
    description: str
    timestamp: datetime | None = None
    is_completed: bool = False
    is_current: bool = False


class OrderTrackingResponse(BaseModel):
    order_id: int
    order_number: str
    current_status: str
    payment_status: str
    delivery_type: str
    steps: list[OrderTrackingStep]
    estimated_delivery: str | None = None

    model_config = ConfigDict(from_attributes=True)
