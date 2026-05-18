from decimal import Decimal


class DeliveryService:
    def calculate_delivery_price(self, *, delivery_type: str) -> Decimal:
        return Decimal("250.00") if delivery_type == "delivery" else Decimal("0")
