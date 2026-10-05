from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.push_notifications import (
    subscribe_push,
    unsubscribe_push,
    get_push_status,
)
from source.errors.auth import InvalidPaymentWebhookPayloadError
from source.schemas.pydantic.push_subscription import (
    PushSubscriptionCreate,
    PushSubscriptionKeys,
)
from source.services.loyalty import LoyaltyService
from source.services.payment import PaymentProviderService
from source.tests.unit.services.test_payment_service import (
    build_payment,
    build_webhook_body,
    execute_webhook,
)


@pytest.mark.asyncio
async def test_bonus_write_off_does_not_commit_and_links_order():
    repository = AsyncMock()
    repository.get_or_create_account.return_value = SimpleNamespace(balance=120)
    session, commiter = AsyncMock(), AsyncMock()
    spent = await LoyaltyService().write_off_points(
        session=session,
        commiter=commiter,
        loyalty_repository=repository,
        user_id=1,
        points_to_spend=200,
        order_id=42,
    )
    assert spent == 120
    commiter.commit.assert_not_awaited()
    session.flush.assert_awaited_once()
    assert repository.add_transaction.call_args.kwargs["order_id"] == 42
    assert repository.add_transaction.call_args.kwargs["amount"] == -120


@pytest.mark.asyncio
async def test_late_cancel_cannot_overwrite_paid_payment():
    result = await execute_webhook(
        body=build_webhook_body(event="payment.canceled"),
        payment=build_payment(status="paid"),
    )
    assert result.payment_repository.updated_status is None
    assert result.order_repository.updated_payment_status is None
    assert result.log_repository.logs[0].processing_status == "ignored"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "amount,currency", [("1.00", "RUB"), ("2650.00", "USD"), ("NaN", "RUB")]
)
async def test_payment_event_rejects_wrong_amount_or_currency(amount, currency):
    body = json.loads(build_webhook_body())
    body["object"]["amount"] = {"value": amount, "currency": currency}
    with pytest.raises(InvalidPaymentWebhookPayloadError):
        await execute_webhook(body=json.dumps(body).encode())


@pytest.mark.asyncio
async def test_duplicate_success_does_not_notify_again():
    result = await execute_webhook(payment=build_payment(status="paid"))
    assert result.notification_service.payment_success == []
    assert result.payment_repository.updated_status is None


@pytest.mark.asyncio
async def test_yookassa_callback_uses_provider_object_not_client_payload(monkeypatch):
    verified = json.loads(build_webhook_body())["object"]

    async def verify(self, **kwargs):
        assert kwargs["method"] == "GET"
        assert kwargs["path"] == "payments/provider-123"
        return verified

    monkeypatch.setattr(PaymentProviderService, "request_yookassa", verify)
    # Test the real service directly, because execute_webhook supplies its own provider fake.
    from source.services.payment_webhook import PaymentWebhookService
    from source.tests.unit.services.test_payment_service import (
        FakePaymentRepository,
        FakePaymentWebhookLogRepository,
        FakeOrderRepository,
        FakeCommiter,
        FakePaymentCacheService,
        FakeOrderCacheService,
        FakeProfileCacheService,
        FakeNotificationService,
        FakeOneCIntegrationService,
        build_order,
    )

    repository = FakePaymentRepository(payment=build_payment())
    forged = json.loads(build_webhook_body())
    forged["object"]["amount"]["value"] = "1.00"
    await PaymentWebhookService().process_webhook(
        raw_body=json.dumps(forged).encode(),
        signature=None,
        session=AsyncMock(),
        commiter=FakeCommiter(),
        redis_service=None,
        payment_provider_service=PaymentProviderService(),
        payment_repository=repository,
        payment_webhook_log_repository=FakePaymentWebhookLogRepository(),
        order_repository=FakeOrderRepository(build_order()),
        payment_cache_service=FakePaymentCacheService(),
        order_cache_service=FakeOrderCacheService(),
        profile_cache_service=FakeProfileCacheService(),
        notification_service=FakeNotificationService(),
        email_service=None,
        telegram_service=None,
        one_c_integration_service=FakeOneCIntegrationService(),
    )
    assert repository.updated_status == "paid"


@pytest.mark.asyncio
async def test_push_cannot_unsubscribe_another_account():
    repo = AsyncMock()
    repo.get_by_endpoint.return_value = SimpleNamespace(user_id=2)
    original = getattr(unsubscribe_push, "__dishka_orig_func__", unsubscribe_push)
    with pytest.raises(HTTPException) as error:
        await original(
            body={"endpoint": "https://push.example/sub"},
            current_user=SimpleNamespace(id=1),
            session=AsyncMock(),
            commiter=AsyncMock(),
            push_subscription_repository=repo,
        )
    assert error.value.status_code == 403
    repo.deactivate.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_transfer_requires_device_keys():
    repo = AsyncMock()
    repo.get_by_endpoint.return_value = SimpleNamespace(
        user_id=2, auth="old", p256dh="old"
    )
    original = getattr(subscribe_push, "__dishka_orig_func__", subscribe_push)
    with pytest.raises(HTTPException) as error:
        await original(
            body=PushSubscriptionCreate(
                endpoint="https://push.example/sub",
                keys=PushSubscriptionKeys(auth="new", p256dh="new"),
            ),
            current_user=SimpleNamespace(id=1),
            session=AsyncMock(),
            commiter=AsyncMock(),
            push_subscription_repository=repo,
        )
    assert error.value.status_code == 403
    repo.save_or_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_status_checks_account_owner(monkeypatch):
    monkeypatch.setattr(
        "source.api.api_v1.views.push_notifications.settings.web_push.enabled", True
    )
    repo = AsyncMock()
    repo.get_by_endpoint.return_value = SimpleNamespace(user_id=2, is_active=True)
    original = getattr(get_push_status, "__dishka_orig_func__", get_push_status)
    response = await original(
        endpoint="https://push.example/sub",
        current_user=SimpleNamespace(id=1),
        session=AsyncMock(),
        push_subscription_repository=repo,
    )
    assert response["is_subscribed"] is False


@pytest.mark.asyncio
async def test_pending_refund_is_not_counted_as_completed(monkeypatch):
    from source.tests.unit.services.test_payment_service import (
        FakeRefundRepository,
        execute_refund_payment,
    )

    monkeypatch.setattr(
        FakeRefundRepository,
        "sum_succeeded_by_payment_id",
        AsyncMock(return_value=Decimal("100")),
    )
    result = await execute_refund_payment(
        amount=Decimal("100"), refunded=Decimal("2550")
    )
    assert result.payment_repository.updated_refund_status == "partial_refunded"


def test_unavailable_cart_item_is_visible_but_not_charged():
    from source.services.cart import CartCalculatorService

    item = SimpleNamespace(
        id=1,
        product_id=5,
        quantity=Decimal("2"),
        name="Нет в наличии",
        price=Decimal("100"),
        unit="шт",
    )
    response = CartCalculatorService().calculate(
        cart_id=1, cart_items=[item], products_by_id={}
    )
    assert len(response.items) == 1
    assert response.items[0].is_available is False
    assert response.items[0].stock_warning
    assert response.final_price == 0
