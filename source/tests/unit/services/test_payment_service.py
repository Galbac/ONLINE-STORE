from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import hashlib
import hmac
import json

import pytest
from source.errors.auth import (
    OrderAccessDeniedError,
    OrderAlreadyPaidError,
    OrderPaymentMethodNotOnlineError,
    PaymentAlreadyConfirmedError,
    PaymentAlreadyPaidError,
    PaymentAccessDeniedError,
    PaymentCancellationStatusNotAllowedError,
    PaymentConfirmationNotSupportedError,
    PaymentNotFoundError,
    PaymentProviderCancelError,
    PaymentProviderCreateError,
    InvalidPaymentWebhookSignatureError,
)
from source.services.order import OrderService
from source.services.payment import PaymentProviderService, PaymentService, ProviderPayment, ProviderPaymentStatus
from source.services.payment_webhook import PaymentWebhookService


class FakeCommiter:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeOrderRepository:
    def __init__(self, order) -> None:
        self.order = order
        self.updated_payment_status = None
        self.updated_status = None

    async def get_by_id(self, *, session, order_id: int):
        return self.order if self.order is not None and self.order.id == order_id else None

    async def update_payment_status(self, *, session, order, payment_status: str):
        order.payment_status = payment_status
        self.updated_payment_status = payment_status
        return order

    async def update_status(self, *, session, order, status: str):
        order.status = status
        self.updated_status = status
        return order


class FakePaymentRepository:
    def __init__(self, active_payment=None, payment=None) -> None:
        self.active_payment = active_payment
        self.payment = payment
        self.created_payment = None
        self.updated_provider_data = False
        self.updated_status = None

    async def get_active_by_order_id(self, *, session, order_id: int):
        return self.active_payment

    async def get_by_id(self, *, session, payment_id: int):
        return self.payment if self.payment is not None and self.payment.id == payment_id else None

    async def get_by_provider_payment_id(self, *, session, provider_payment_id: str):
        return self.payment if self.payment is not None and self.payment.provider_payment_id == provider_payment_id else None

    async def create(self, *, session, order_id: int, amount, currency: str, status: str, provider: str, payment_url):
        self.created_payment = SimpleNamespace(
            id=501,
            order_id=order_id,
            amount=amount,
            currency=currency,
            status=status,
            provider=provider,
            provider_payment_id=None,
            payment_url=payment_url,
            created_date=datetime(2026, 5, 12, 10, 0, 0),
        )
        return self.created_payment

    async def update_provider_data(self, *, session, payment, provider_payment_id: str, payment_url: str, status: str):
        payment.provider_payment_id = provider_payment_id
        payment.payment_url = payment_url
        payment.status = status
        self.updated_provider_data = True
        return payment

    async def update_status(self, *, session, payment, status: str, paid_at=None, cancelled_at=None):
        payment.status = status
        payment.paid_at = paid_at
        payment.cancelled_at = cancelled_at
        self.updated_status = status
        return payment


class FakeProviderService(PaymentProviderService):
    def __init__(
        self,
        *,
        fail: bool = False,
        status: str = "pending",
        confirm_supported: bool = True,
        cancel_fail: bool = False,
    ) -> None:
        self.fail = fail
        self.status = status
        self.confirm_supported = confirm_supported
        self.cancel_fail = cancel_fail
        self.calls = []

    async def create_payment(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise PaymentProviderCreateError
        return ProviderPayment(
            provider_payment_id="provider-123",
            payment_url="https://payment.example.com/pay/123",
            status="pending",
        )

    async def get_payment_status(self, *, provider_payment_id: str):
        self.calls.append({"provider_payment_id": provider_payment_id})
        return ProviderPaymentStatus(
            status=self.status,
            paid_at=datetime(2026, 5, 12, 10, 5, 0) if self.status == "paid" else None,
        )

    async def confirm_payment(self, *, provider_payment_id: str, amount=None):
        self.calls.append({"provider_payment_id": provider_payment_id, "amount": amount})
        if not self.confirm_supported:
            raise PaymentConfirmationNotSupportedError
        return ProviderPaymentStatus(
            status=self.status,
            paid_at=datetime(2026, 5, 12, 10, 10, 0) if self.status in {"paid", "succeeded"} else None,
        )

    async def cancel_payment(self, *, provider_payment_id: str, reason=None):
        self.calls.append({"provider_payment_id": provider_payment_id, "reason": reason})
        if self.cancel_fail:
            raise PaymentProviderCancelError
        return ProviderPaymentStatus(status="cancelled")


class FakeOrderCacheService:
    def __init__(self) -> None:
        self.invalidated = []

    async def invalidate_order(self, *, redis_service, user_id: int, order_id: int) -> None:
        self.invalidated.append((user_id, order_id))


class FakePaymentCacheService:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}
        self.invalidated = []

    async def get_detail(self, *, redis_service, user_id: int, payment_id: int):
        return self.values.get((user_id, payment_id))

    async def set_detail(self, *, redis_service, user_id: int, payment_id: int, response, ttl_seconds: int):
        self.values[(user_id, payment_id)] = response
        self.ttls[(user_id, payment_id)] = ttl_seconds

    async def invalidate_detail(self, *, redis_service, user_id: int, payment_id: int):
        self.values.pop((user_id, payment_id), None)

    async def invalidate_payment(self, *, redis_service, user_id: int, payment_id: int):
        self.invalidated.append((user_id, payment_id))


class FakePaymentWebhookLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def exists_by_event_id(self, *, session, provider_event_id: str):
        return any(log.provider_event_id == provider_event_id for log in self.logs)

    async def create(self, **kwargs):
        log = SimpleNamespace(**kwargs)
        self.logs.append(log)
        return log


class FakeProfileCacheService:
    def __init__(self) -> None:
        self.deleted = []

    async def delete_summary(self, *, redis_service, user_id: int):
        self.deleted.append(user_id)


class FakeNotificationService:
    def __init__(self) -> None:
        self.payment_success = []

    async def notify_payment_success(self, **kwargs):
        self.payment_success.append(kwargs["order"].id)


class FakeOneCIntegrationService:
    def __init__(self) -> None:
        self.marked = []

    async def mark_order_pending_sync(self, *, order):
        self.marked.append(order.id)


class DummyEmailService:
    pass


class DummyTelegramService:
    pass


def build_order(
    *,
    user_id: int = 1,
    payment_method: str = "online",
    payment_status: str = "unpaid",
):
    return SimpleNamespace(
        id=101,
        user_id=user_id,
        order_number="ORD-000101",
        final_price=Decimal("2650.00"),
        status="pending_payment",
        payment_method=payment_method,
        payment_status=payment_status,
        customer_email="ivan@example.com",
    )


def build_payment(*, status: str = "pending"):
    return SimpleNamespace(
        id=500,
        order_id=101,
        amount=Decimal("2650.00"),
        currency="RUB",
        status=status,
        provider="yookassa",
        provider_payment_id="provider-123",
        payment_url="https://payment.example.com/pay/existing",
        paid_at=None,
        cancelled_at=None,
        created_date=datetime(2026, 5, 12, 9, 0, 0),
        updated_date=datetime(2026, 5, 12, 9, 5, 0),
        provider_secret="secret",
        raw_webhook_payload={"secret": True},
    )


async def execute_create_payment(*, order=None, active_payment=None, provider_fail=False):
    order = build_order() if order is None else order
    payment_repository = FakePaymentRepository(active_payment=active_payment)
    order_repository = FakeOrderRepository(order)
    provider_service = FakeProviderService(fail=provider_fail)
    order_cache_service = FakeOrderCacheService()
    commiter = FakeCommiter()
    response = await PaymentService().create_payment(
        session=None,
        commiter=commiter,
        redis_service=None,
        user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
        order=order,
        order_repository=order_repository,
        payment_repository=payment_repository,
        order_service=OrderService(),
        payment_provider_service=provider_service,
        order_cache_service=order_cache_service,
    )
    return SimpleNamespace(
        response=response,
        payment_repository=payment_repository,
        order_repository=order_repository,
        provider_service=provider_service,
        order_cache_service=order_cache_service,
        commiter=commiter,
    )


async def execute_get_payment_detail(*, order=None, payment="default", provider_status="pending"):
    order = build_order() if order is None else order
    payment = build_payment() if payment == "default" else payment
    payment_repository = FakePaymentRepository(payment=payment)
    order_repository = FakeOrderRepository(order)
    provider_service = FakeProviderService(status=provider_status)
    payment_cache_service = FakePaymentCacheService()
    order_cache_service = FakeOrderCacheService()
    commiter = FakeCommiter()
    response = await PaymentService().get_payment_detail(
        session=None,
        commiter=commiter,
        redis_service=None,
        user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
        payment_id=500,
        payment_repository=payment_repository,
        order_repository=order_repository,
        payment_provider_service=provider_service,
        payment_cache_service=payment_cache_service,
        order_cache_service=order_cache_service,
    )
    return SimpleNamespace(
        response=response,
        payment_repository=payment_repository,
        order_repository=order_repository,
        provider_service=provider_service,
        payment_cache_service=payment_cache_service,
        order_cache_service=order_cache_service,
        commiter=commiter,
    )


async def execute_confirm_payment(*, order=None, payment=None, provider_status="paid", confirm_supported=True):
    order = build_order() if order is None else order
    payment = build_payment(status="waiting_for_capture") if payment is None else payment
    payment_repository = FakePaymentRepository(payment=payment)
    order_repository = FakeOrderRepository(order)
    provider_service = FakeProviderService(status=provider_status, confirm_supported=confirm_supported)
    payment_cache_service = FakePaymentCacheService()
    order_cache_service = FakeOrderCacheService()
    commiter = FakeCommiter()
    response = await PaymentService().confirm_payment(
        session=None,
        commiter=commiter,
        redis_service=None,
        user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
        payment_id=500,
        amount=None,
        payment_repository=payment_repository,
        order_repository=order_repository,
        payment_provider_service=provider_service,
        payment_cache_service=payment_cache_service,
        order_cache_service=order_cache_service,
    )
    return SimpleNamespace(
        response=response,
        payment_repository=payment_repository,
        order_repository=order_repository,
        provider_service=provider_service,
        payment_cache_service=payment_cache_service,
        order_cache_service=order_cache_service,
        commiter=commiter,
    )


async def execute_cancel_payment(*, order=None, payment="default", cancel_fail=False):
    order = build_order() if order is None else order
    payment = build_payment(status="pending") if payment == "default" else payment
    payment_repository = FakePaymentRepository(payment=payment)
    order_repository = FakeOrderRepository(order)
    provider_service = FakeProviderService(cancel_fail=cancel_fail)
    payment_cache_service = FakePaymentCacheService()
    order_cache_service = FakeOrderCacheService()
    commiter = FakeCommiter()
    response = await PaymentService().cancel_payment(
        session=None,
        commiter=commiter,
        redis_service=None,
        user=SimpleNamespace(id=1, is_active=True, is_deleted=False),
        payment_id=500,
        reason="Передумал оплачивать онлайн",
        payment_repository=payment_repository,
        order_repository=order_repository,
        payment_provider_service=provider_service,
        payment_cache_service=payment_cache_service,
        order_cache_service=order_cache_service,
    )
    return SimpleNamespace(
        response=response,
        payment_repository=payment_repository,
        order_repository=order_repository,
        provider_service=provider_service,
        payment_cache_service=payment_cache_service,
        order_cache_service=order_cache_service,
        commiter=commiter,
    )


def build_webhook_body(*, event="payment.succeeded", event_id="evt-1", provider_payment_id="provider-123"):
    return json.dumps(
        {
            "id": event_id,
            "event": event,
            "object": {
                "id": provider_payment_id,
                "status": "succeeded",
                "metadata": {"payment_id": "500"},
            },
        },
    ).encode("utf-8")


async def execute_webhook(*, body=None, payment="default", order=None, log_repository=None):
    body = build_webhook_body() if body is None else body
    payment = build_payment() if payment == "default" else payment
    order = build_order() if order is None else order
    payment_repository = FakePaymentRepository(payment=payment)
    order_repository = FakeOrderRepository(order)
    log_repository = FakePaymentWebhookLogRepository() if log_repository is None else log_repository
    payment_cache_service = FakePaymentCacheService()
    order_cache_service = FakeOrderCacheService()
    profile_cache_service = FakeProfileCacheService()
    notification_service = FakeNotificationService()
    one_c_service = FakeOneCIntegrationService()
    commiter = FakeCommiter()
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    response = await PaymentWebhookService().process_webhook(
        raw_body=body,
        signature=signature,
        session=None,
        commiter=commiter,
        redis_service=None,
        payment_provider_service=PaymentProviderService(),
        payment_repository=payment_repository,
        payment_webhook_log_repository=log_repository,
        order_repository=order_repository,
        payment_cache_service=payment_cache_service,
        order_cache_service=order_cache_service,
        profile_cache_service=profile_cache_service,
        notification_service=notification_service,
        email_service=DummyEmailService(),
        telegram_service=DummyTelegramService(),
        one_c_integration_service=one_c_service,
    )
    return SimpleNamespace(
        response=response,
        payment_repository=payment_repository,
        order_repository=order_repository,
        log_repository=log_repository,
        payment_cache_service=payment_cache_service,
        order_cache_service=order_cache_service,
        profile_cache_service=profile_cache_service,
        notification_service=notification_service,
        one_c_service=one_c_service,
        commiter=commiter,
    )


@pytest.mark.asyncio
async def test_create_payment_success():
    result = await execute_create_payment()

    assert result.response.id == 501
    assert result.response.payment_url == "https://payment.example.com/pay/123"
    assert result.response.status == "pending"
    assert result.order_repository.updated_payment_status == "pending"
    assert result.payment_repository.updated_provider_data is True
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_create_payment_returns_existing_active_payment():
    result = await execute_create_payment(active_payment=build_payment())

    assert result.response.id == 500
    assert result.response.payment_url == "https://payment.example.com/pay/existing"
    assert result.payment_repository.created_payment is None
    assert result.provider_service.calls == []


@pytest.mark.asyncio
async def test_create_payment_rejects_foreign_order():
    with pytest.raises(OrderAccessDeniedError):
        await execute_create_payment(order=build_order(user_id=2))


@pytest.mark.asyncio
async def test_create_payment_rejects_paid_order():
    with pytest.raises(OrderAlreadyPaidError):
        await execute_create_payment(order=build_order(payment_status="paid"))


@pytest.mark.asyncio
async def test_create_payment_rejects_on_delivery_order():
    with pytest.raises(OrderPaymentMethodNotOnlineError):
        await execute_create_payment(order=build_order(payment_method="on_delivery"))


@pytest.mark.asyncio
async def test_create_payment_reports_order_not_found():
    repository = FakeOrderRepository(None)
    order = await repository.get_by_id(session=None, order_id=101)

    assert order is None


@pytest.mark.asyncio
async def test_create_payment_rolls_back_on_provider_error():
    with pytest.raises(PaymentProviderCreateError):
        await execute_create_payment(provider_fail=True)


@pytest.mark.asyncio
async def test_create_payment_invalidates_order_cache():
    result = await execute_create_payment()

    assert result.order_cache_service.invalidated == [(1, 101)]


@pytest.mark.asyncio
async def test_get_payment_detail_success(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.status_sync_enabled", False)

    result = await execute_get_payment_detail()

    assert result.response.id == 500
    assert result.response.order_number == "ORD-000101"
    assert result.payment_cache_service.ttls[(1, 500)] == 30


@pytest.mark.asyncio
async def test_get_payment_detail_rejects_foreign_payment(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.status_sync_enabled", False)

    with pytest.raises(PaymentAccessDeniedError):
        await execute_get_payment_detail(order=build_order(user_id=2))


@pytest.mark.asyncio
async def test_get_payment_detail_reports_missing_payment(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.status_sync_enabled", False)

    with pytest.raises(PaymentNotFoundError):
        await execute_get_payment_detail(payment=None)


@pytest.mark.asyncio
async def test_get_payment_detail_updates_status_from_provider(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.status_sync_enabled", True)

    result = await execute_get_payment_detail(provider_status="paid")

    assert result.response.status == "paid"
    assert result.response.paid_at == datetime(2026, 5, 12, 10, 5, 0)
    assert result.payment_repository.updated_status == "paid"
    assert result.order_repository.updated_payment_status == "paid"
    assert result.order_cache_service.invalidated == [(1, 101)]
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_get_payment_detail_does_not_return_secret_fields(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.status_sync_enabled", False)

    result = await execute_get_payment_detail()
    payload = result.response.model_dump()

    assert "provider_secret" not in payload
    assert "raw_webhook_payload" not in payload


@pytest.mark.asyncio
async def test_confirm_payment_success(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.capture_mode", "manual")

    result = await execute_confirm_payment(provider_status="succeeded")

    assert result.response.status == "paid"
    assert result.response.paid_at == datetime(2026, 5, 12, 10, 10, 0)
    assert result.order_repository.updated_payment_status == "paid"
    assert result.order_repository.updated_status == "new"
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_confirm_payment_rejects_foreign_payment(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.capture_mode", "manual")

    with pytest.raises(PaymentAccessDeniedError):
        await execute_confirm_payment(order=build_order(user_id=2))


@pytest.mark.asyncio
async def test_confirm_payment_rejects_paid_payment(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.capture_mode", "manual")

    with pytest.raises(PaymentAlreadyConfirmedError):
        await execute_confirm_payment(payment=build_payment(status="paid"))


@pytest.mark.asyncio
async def test_confirm_payment_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.capture_mode", "manual")

    with pytest.raises(PaymentConfirmationNotSupportedError):
        await execute_confirm_payment(confirm_supported=False)


@pytest.mark.asyncio
async def test_confirm_payment_marks_order_paid(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.capture_mode", "manual")

    result = await execute_confirm_payment()

    assert result.order_repository.updated_payment_status == "paid"


@pytest.mark.asyncio
async def test_webhook_processes_payment_succeeded(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.provider_webhook_secret", "secret")
    monkeypatch.setattr("source.services.payment.settings.payments.webhook_verify_signature", True)

    result = await execute_webhook()

    assert result.response.message == "Webhook processed"
    assert result.payment_repository.updated_status == "paid"
    assert result.order_repository.updated_payment_status == "paid"
    assert result.order_repository.updated_status == "new"
    assert result.notification_service.payment_success == [101]
    assert result.one_c_service.marked == [101]


@pytest.mark.asyncio
async def test_webhook_processes_payment_canceled(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.provider_webhook_secret", "secret")
    monkeypatch.setattr("source.services.payment.settings.payments.webhook_verify_signature", True)

    result = await execute_webhook(body=build_webhook_body(event="payment.canceled", event_id="evt-2"))

    assert result.payment_repository.updated_status == "cancelled"
    assert result.order_repository.updated_payment_status == "cancelled"


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.provider_webhook_secret", "secret")
    monkeypatch.setattr("source.services.payment.settings.payments.webhook_verify_signature", True)

    with pytest.raises(InvalidPaymentWebhookSignatureError):
        await PaymentWebhookService().process_webhook(
            raw_body=build_webhook_body(),
            signature="bad",
            session=None,
            commiter=FakeCommiter(),
            redis_service=None,
            payment_provider_service=PaymentProviderService(),
            payment_repository=FakePaymentRepository(payment=build_payment()),
            payment_webhook_log_repository=FakePaymentWebhookLogRepository(),
            order_repository=FakeOrderRepository(build_order()),
            payment_cache_service=FakePaymentCacheService(),
            order_cache_service=FakeOrderCacheService(),
            profile_cache_service=FakeProfileCacheService(),
            notification_service=FakeNotificationService(),
            email_service=DummyEmailService(),
            telegram_service=DummyTelegramService(),
            one_c_integration_service=FakeOneCIntegrationService(),
        )


@pytest.mark.asyncio
async def test_webhook_is_idempotent(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.provider_webhook_secret", "secret")
    monkeypatch.setattr("source.services.payment.settings.payments.webhook_verify_signature", True)
    logs = FakePaymentWebhookLogRepository()

    first = await execute_webhook(log_repository=logs)
    second = await execute_webhook(log_repository=logs)

    assert first.payment_repository.updated_status == "paid"
    assert second.payment_repository.updated_status is None
    assert len(logs.logs) == 1


@pytest.mark.asyncio
async def test_webhook_logs_missing_payment(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.provider_webhook_secret", "secret")
    monkeypatch.setattr("source.services.payment.settings.payments.webhook_verify_signature", True)

    result = await execute_webhook(payment=None)

    assert result.response.message == "Webhook processed"
    assert result.log_repository.logs[0].processing_status == "payment_not_found"


@pytest.mark.asyncio
async def test_webhook_invalidates_redis_cache(monkeypatch):
    monkeypatch.setattr("source.services.payment.settings.payments.provider_webhook_secret", "secret")
    monkeypatch.setattr("source.services.payment.settings.payments.webhook_verify_signature", True)

    result = await execute_webhook()

    assert result.payment_cache_service.invalidated == [(1, 500)]
    assert result.order_cache_service.invalidated == [(1, 101)]
    assert result.profile_cache_service.deleted == [1]


@pytest.mark.asyncio
async def test_cancel_payment_success():
    result = await execute_cancel_payment()

    assert result.response.message == "Платёж отменён"
    assert result.response.payment.status == "cancelled"
    assert result.response.payment.cancelled_at is not None
    assert result.order_repository.updated_payment_status == "unpaid"
    assert result.payment_cache_service.values == {}
    assert result.order_cache_service.invalidated == [(1, 101)]
    assert result.commiter.committed is True


@pytest.mark.asyncio
async def test_cancel_payment_rejects_paid_payment():
    with pytest.raises(PaymentAlreadyPaidError):
        await execute_cancel_payment(payment=build_payment(status="paid"))


@pytest.mark.asyncio
async def test_cancel_payment_rejects_foreign_payment():
    with pytest.raises(PaymentAccessDeniedError):
        await execute_cancel_payment(order=build_order(user_id=2))


@pytest.mark.asyncio
async def test_cancel_payment_reports_missing_payment():
    with pytest.raises(PaymentNotFoundError):
        await execute_cancel_payment(payment=None)


@pytest.mark.asyncio
async def test_cancel_payment_reports_provider_error():
    with pytest.raises(PaymentProviderCancelError):
        await execute_cancel_payment(cancel_fail=True)
