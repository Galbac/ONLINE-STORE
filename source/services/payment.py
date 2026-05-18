from source.schemas.pydantic.order import OrderCreateResponse


class PaymentService:
    async def create_payment(self, *, payment_repository, session, order) -> str:
        payment_url = f"https://payment.example.com/pay/{order.id}"
        await payment_repository.create(
            session=session,
            order_id=order.id,
            amount=order.final_price,
            status="unpaid",
            payment_url=payment_url,
        )
        return payment_url
