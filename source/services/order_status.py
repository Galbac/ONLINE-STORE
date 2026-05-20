from source.errors.auth import OrderInvalidStatusError, OrderStatusTransitionError


ORDER_STATUSES = {
    "pending_payment",
    "new",
    "confirmed",
    "awaiting_confirmation",
    "assembling",
    "assembled",
    "ready_for_pickup",
    "delivering",
    "delivered",
    "completed",
    "cancelled",
}

ORDER_STATUS_TRANSITIONS = {
    "pending_payment": {"new", "cancelled"},
    "new": {"confirmed", "awaiting_confirmation", "assembling", "cancelled"},
    "confirmed": {"assembling", "cancelled"},
    "awaiting_confirmation": {"confirmed", "assembling", "cancelled"},
    "assembling": {"assembled", "delivering"},
    "assembled": {"ready_for_pickup", "delivering", "completed"},
    "ready_for_pickup": {"completed"},
    "delivering": {"delivered", "completed"},
    "delivered": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


class OrderStatusService:
    def validate_transition(self, *, current_status: str, new_status: str) -> None:
        if new_status not in ORDER_STATUSES:
            raise OrderInvalidStatusError
        if current_status == new_status:
            return
        if new_status not in ORDER_STATUS_TRANSITIONS.get(current_status, set()):
            raise OrderStatusTransitionError

    def affects_one_c(self, *, status: str) -> bool:
        return status in ORDER_STATUSES - {"pending_payment"}
