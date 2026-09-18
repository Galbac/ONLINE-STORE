from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.order import Order
from source.db.models.user import User
from source.repositories.order import OrderRepository
from source.repositories.order_status_history import OrderStatusHistoryRepository
from source.schemas.pydantic.order_tracking import OrderTrackingResponse, OrderTrackingStep


class OrderTrackingService:
    async def get_tracking(
        self,
        *,
        session: AsyncSession,
        order_repository: OrderRepository,
        order_status_history_repository: OrderStatusHistoryRepository,
        user: User,
        order_id: int,
    ) -> OrderTrackingResponse | None:
        order = await order_repository.get_by_id(session=session, order_id=order_id)
        if order is None:
            return None

        # Check ownership unless staff
        if order.user_id != user.id and user.role == "customer":
            return None

        history = await order_status_history_repository.get_by_order_id(session=session, order_id=order_id)
        history_map = {h.status: h.created_date for h in history}

        is_cancelled = order.status == "cancelled"

        all_steps = [
            ("created", "Заказ оформлен", "Мы получили ваш заказ и проверяем позиции"),
            ("confirmed", "Подтвержден", "Заказ подтвержден и отправлен на сборку"),
            ("assembling", "Сборка заказа", "Сборщик комплектует самые свежие продукты"),
            ("in_delivery", "Курьер в пути", "Заказ передан в доставку и направляется к вам"),
            ("delivered", "Доставлен", "Заказ успешно вручен покупателю"),
        ]

        # Determine index of current status
        status_indices = {step[0]: i for i, step in enumerate(all_steps)}
        current_idx = status_indices.get(order.status, 0)

        steps: list[OrderTrackingStep] = []
        if is_cancelled:
            steps.append(
                OrderTrackingStep(
                    step_key="created",
                    title="Заказ оформлен",
                    description="Заказ был создан",
                    timestamp=order.created_date,
                    is_completed=True,
                    is_current=False,
                )
            )
            steps.append(
                OrderTrackingStep(
                    step_key="cancelled",
                    title="Заказ отменен",
                    description=order.cancel_reason or "Заказ был отменен",
                    timestamp=order.cancelled_at or order.updated_date,
                    is_completed=True,
                    is_current=True,
                )
            )
        else:
            for i, (key, title, desc) in enumerate(all_steps):
                is_completed = i <= current_idx
                is_current = i == current_idx
                step_timestamp = history_map.get(key)
                if i == 0 and not step_timestamp:
                    step_timestamp = order.created_date

                steps.append(
                    OrderTrackingStep(
                        step_key=key,
                        title=title,
                        description=desc,
                        timestamp=step_timestamp,
                        is_completed=is_completed,
                        is_current=is_current,
                    )
                )

        est_delivery = "Сегодня в течение 45-60 минут" if order.status in {"confirmed", "assembling", "in_delivery"} else None

        return OrderTrackingResponse(
            order_id=order.id,
            order_number=order.order_number,
            current_status=order.status,
            payment_status=order.payment_status or "pending",
            delivery_type=order.delivery_type,
            steps=steps,
            estimated_delivery=est_delivery,
        )
