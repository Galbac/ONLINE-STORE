import asyncio
import json
from typing import Any

from pywebpush import WebPushException, webpush
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.logging import logger
from source.config.settings import settings
from source.db.models.push_subscription import PushSubscription
from source.repositories.push_subscription import PushSubscriptionRepository


class WebPushService:
    def get_public_key(self) -> str:
        return settings.web_push.vapid_public_key

    def _send_webpush_sync(
        self,
        *,
        subscription_info: dict[str, Any],
        payload_json: str,
        ttl: int = 86400,
    ) -> None:
        webpush(
            subscription_info=subscription_info,
            data=payload_json,
            vapid_private_key=settings.web_push.vapid_private_key,
            vapid_claims={"sub": settings.web_push.vapid_claims_email},
            ttl=ttl,
        )

    async def send_to_subscription(
        self,
        *,
        session: AsyncSession,
        push_subscription_repository: PushSubscriptionRepository,
        subscription: PushSubscription,
        title: str,
        body: str,
        url: str = "/",
        icon: str | None = None,
        badge: str | None = None,
        tag: str | None = None,
    ) -> bool:
        if not settings.web_push.enabled:
            logger.info("Web Push notifications are disabled in settings")
            return False

        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        payload = json.dumps(
            {
                "title": title,
                "body": body,
                "url": url,
                "icon": icon or "/icons/icon-192x192.png",
                "badge": badge or "/icons/badge-72x72.png",
                "tag": tag or "grocery_push",
                "data": {"url": url},
            },
            ensure_ascii=False,
        )

        try:
            await asyncio.to_thread(
                self._send_webpush_sync,
                subscription_info=subscription_info,
                payload_json=payload,
            )
            return True
        except WebPushException as ex:
            status_code = ex.response.status_code if ex.response is not None else None
            logger.warning(
                "WebPushException sending to %s: status=%s, msg=%s",
                subscription.endpoint[:40],
                status_code,
                str(ex),
            )
            # Если браузер отписался или эндпоинт истек (404/410), деактивируем
            if status_code in (404, 410):
                await push_subscription_repository.deactivate(
                    session=session,
                    endpoint=subscription.endpoint,
                )
            return False
        except Exception as ex:
            logger.exception("Unexpected error sending Web Push: %s", str(ex))
            return False

    async def send_to_user(
        self,
        *,
        session: AsyncSession,
        push_subscription_repository: PushSubscriptionRepository,
        user_id: int,
        title: str,
        body: str,
        url: str = "/",
        icon: str | None = None,
        badge: str | None = None,
        tag: str | None = None,
    ) -> int:
        if not settings.web_push.enabled:
            return 0

        subscriptions = await push_subscription_repository.get_active_by_user_id(
            session=session,
            user_id=user_id,
        )
        if not subscriptions:
            return 0

        sent_count = 0
        for sub in subscriptions:
            ok = await self.send_to_subscription(
                session=session,
                push_subscription_repository=push_subscription_repository,
                subscription=sub,
                title=title,
                body=body,
                url=url,
                icon=icon,
                badge=badge,
                tag=tag,
            )
            if ok:
                sent_count += 1
        return sent_count

    async def broadcast(
        self,
        *,
        session: AsyncSession,
        push_subscription_repository: PushSubscriptionRepository,
        title: str,
        body: str,
        url: str = "/",
        icon: str | None = None,
        badge: str | None = None,
        tag: str | None = None,
    ) -> tuple[int, int]:
        subscriptions = await push_subscription_repository.get_all_active(session=session)
        sent = 0
        failed = 0
        for sub in subscriptions:
            ok = await self.send_to_subscription(
                session=session,
                push_subscription_repository=push_subscription_repository,
                subscription=sub,
                title=title,
                body=body,
                url=url,
                icon=icon,
                badge=badge,
                tag=tag,
            )
            if ok:
                sent += 1
            else:
                failed += 1
        return sent, failed
