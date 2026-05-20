class OneCIntegrationService:
    async def mark_order_pending_sync(self, *, order) -> None:
        order.sync_status = "pending"

    async def mark_order_cancel_pending_sync(self, *, order) -> None:
        order.sync_status = "pending_cancel" if order.sync_status not in {"pending", "cancelled", "no_sync_needed"} else "cancelled"

    async def mark_cancel_pending(self, *, order) -> None:
        await self.mark_order_cancel_pending_sync(order=order)
