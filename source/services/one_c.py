class OneCIntegrationService:
    async def mark_order_pending_sync(self, *, order) -> None:
        order.sync_status = "pending"
