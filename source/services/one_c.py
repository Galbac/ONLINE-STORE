import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from source.config.settings import settings
from source.errors.auth import OneCSyncError


class OneCIntegrationService:
    async def mark_order_pending_sync(self, *, order) -> None:
        order.sync_status = "pending"

    async def mark_order_cancel_pending_sync(self, *, order) -> None:
        order.sync_status = "pending_cancel" if order.sync_status not in {"pending", "cancelled", "no_sync_needed"} else "cancelled"

    async def mark_cancel_pending(self, *, order) -> None:
        await self.mark_order_cancel_pending_sync(order=order)

    async def sync_order(self, *, payload: dict) -> dict:
        if not settings.one_c.api_url:
            raise OneCSyncError("1C API URL is not configured")

        url = settings.one_c.api_url.rstrip("/") + "/orders"
        headers = {"Content-Type": "application/json"}
        if settings.one_c.api_token:
            headers["Authorization"] = f"Bearer {settings.one_c.api_token}"

        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="ignore")
            raise OneCSyncError(error_body or f"1C HTTP error {error.code}") from error
        except URLError as error:
            raise OneCSyncError(str(error.reason)) from error

        if not response_body:
            return {}
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as error:
            raise OneCSyncError("Invalid 1C response") from error
