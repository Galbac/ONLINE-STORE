from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from source.errors.auth import (
    OrderAccessDeniedError,
    OrderAlreadyPaidError,
    OrderPaymentMethodNotOnlineError,
    PaymentProviderCreateError,
)
from source.services.order import OrderService
from source.services.payment import PaymentProviderService, PaymentService, ProviderPayment


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

    async def get_by_id(self, *, session, order_id: int):
        return self.order if self.order is not None and self.order.id == order_id else None

    async def update_payment_status(self, *, session, order, payment_status: str):
        order.payment_status = payment_status
        self.updated_payment_status = payment_status
        return order


class FakePaymentRepository:
    def __init__(self, active_payment=None) -> None:
        self.active_payment = active_payment
        self.created_payment = None
        self.updated_provider_data = False

    async def get_active_by_order_id(self, *, session, order_id: int):
        return self.active_payment

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


class FakeProviderService(PaymentProviderService):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
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


class FakeOrderCacheService:
    def __init__(self) -> None:
        self.invalidated = []

    async def invalidate_order(self, *, redis_service, user_id: int, order_id: int) -> None:
        self.invalidated.append((user_id, order_id))


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


def build_payment():
    return SimpleNamespace(
        id=500,
        amount=Decimal("2650.00"),
        currency="RUB",
        status="pending",
        provider="yookassa",
        payment_url="https://payment.example.com/pay/existing",
        created_date=datetime(2026, 5, 12, 9, 0, 0),
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
