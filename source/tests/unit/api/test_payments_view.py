from datetime import datetime, UTC
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.payments import (
    cancel_payment,
    confirm_payment,
    create_payment,
    get_payment_detail,
    process_payment_webhook,
    refund_payment,
)
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import (
    InvalidPaymentWebhookSignatureError,
    PaymentNotFoundError,
)
from source.schemas.pydantic.payment import (
    PaymentCancelPaymentResponse,
    PaymentCancelRequest,
    PaymentCancelResponse,
    PaymentConfirmRequest,
    PaymentConfirmResponse,
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailResponse,
    PaymentRefundRequest,
    PaymentRefundResponse,
    RefundResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def active_user():
    return User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True)


@pytest.fixture
def admin_user():
    return User(id=2, name="Админ", role=UserRole.ADMIN, is_active=True)


@pytest.fixture
def fake_payment_detail():
    now = datetime.now(UTC)
    return PaymentDetailResponse(
        id=1,
        order_id=10,
        order_number="ORD-000010",
        amount=Decimal("1500.00"),
        currency="RUB",
        status="pending",
        provider="yookassa",
        payment_url="https://pay.example.com/invoice/123",
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------
# POST /payments/create
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_create_payment_success(active_user):
    now = datetime.now(UTC)
    service = AsyncMock()
    service.create_payment.return_value = PaymentCreateResponse(
        id=1,
        order_id=10,
        order_number="ORD-000010",
        amount=Decimal("1500.00"),
        currency="RUB",
        status="pending",
        provider="yookassa",
        payment_url="https://pay.example.com/invoice/123",
        created_at=now,
    )

    order_repo = AsyncMock()
    order_repo.get_by_id.return_value = SimpleNamespace(id=10, user_id=1)

    body = PaymentCreateRequest(order_id=10)
    response = await unwrap(create_payment)(
        body=body,
        current_user=active_user,
        session=AsyncMock(),
        commiter=AsyncMock(),
        redis_service=AsyncMock(),
        order_service=AsyncMock(),
        order_repository=order_repo,
        payment_repository=AsyncMock(),
        payment_service=service,
        payment_provider_service=AsyncMock(),
        order_cache_service=AsyncMock(),
    )

    assert response.id == 1
    assert response.status == "pending"
    assert "pay.example.com" in response.payment_url


@pytest.mark.asyncio
async def test_create_payment_order_not_found(active_user):
    order_repo = AsyncMock()
    order_repo.get_by_id.return_value = None

    body = PaymentCreateRequest(order_id=999)
    with pytest.raises(HTTPException) as exc:
        await unwrap(create_payment)(
            body=body,
            current_user=active_user,
            session=AsyncMock(),
            commiter=AsyncMock(),
            redis_service=AsyncMock(),
            order_service=AsyncMock(),
            order_repository=order_repo,
            payment_repository=AsyncMock(),
            payment_service=AsyncMock(),
            payment_provider_service=AsyncMock(),
            order_cache_service=AsyncMock(),
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------
# GET /payments/{payment_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_payment_detail_success(active_user, fake_payment_detail):
    service = AsyncMock()
    service.get_payment_detail.return_value = fake_payment_detail

    response = await unwrap(get_payment_detail)(
        payment_id=1,
        current_user=active_user,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        payment_service=service,
        payment_cache_service=AsyncMock(),
        payment_repository=AsyncMock(),
        order_repository=AsyncMock(),
    )

    assert response.id == 1
    assert response.amount == Decimal("1500.00")


@pytest.mark.asyncio
async def test_get_payment_detail_not_found(active_user):
    service = AsyncMock()
    service.get_payment_detail.side_effect = PaymentNotFoundError

    with pytest.raises(HTTPException) as exc:
        await unwrap(get_payment_detail)(
            payment_id=999,
            current_user=active_user,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            payment_service=service,
            payment_cache_service=AsyncMock(),
            payment_repository=AsyncMock(),
            order_repository=AsyncMock(),
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------
# POST /payments/{payment_id}/confirm
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_payment_success(admin_user):
    service = AsyncMock()
    service.confirm_payment.return_value = PaymentConfirmResponse(
        id=1,
        order_id=10,
        status="succeeded",
        amount=Decimal("1500.00"),
        currency="RUB",
    )

    body = PaymentConfirmRequest()
    response = await unwrap(confirm_payment)(
        payment_id=1,
        body=body,
        current_user=admin_user,
        session=AsyncMock(),
        commiter=AsyncMock(),
        redis_service=AsyncMock(),
        order_repository=AsyncMock(),
        payment_repository=AsyncMock(),
        payment_service=service,
        payment_provider_service=AsyncMock(),
        payment_cache_service=AsyncMock(),
        order_cache_service=AsyncMock(),
    )

    assert response.status == "succeeded"


# ---------------------------------------------------------
# POST /payments/{payment_id}/cancel
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_payment_success(admin_user):
    service = AsyncMock()
    service.cancel_payment.return_value = PaymentCancelResponse(
        message="Платеж успешно отменен",
        payment=PaymentCancelPaymentResponse(
            id=1,
            order_id=10,
            status="canceled",
            amount=Decimal("1500.00"),
            currency="RUB",
        ),
    )

    body = PaymentCancelRequest()
    response = await unwrap(cancel_payment)(
        payment_id=1,
        body=body,
        current_user=admin_user,
        session=AsyncMock(),
        commiter=AsyncMock(),
        redis_service=AsyncMock(),
        order_repository=AsyncMock(),
        payment_repository=AsyncMock(),
        payment_service=service,
        payment_provider_service=AsyncMock(),
        payment_cache_service=AsyncMock(),
        order_cache_service=AsyncMock(),
    )

    assert response.payment.status == "canceled"


# ---------------------------------------------------------
# POST /payments/{payment_id}/refund
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_refund_payment_success(admin_user):
    now = datetime.now(UTC)
    service = AsyncMock()
    service.refund_payment.return_value = PaymentRefundResponse(
        message="Возврат успешно выполнен",
        refund=RefundResponse(
            id=1,
            payment_id=1,
            order_id=10,
            amount=Decimal("500.00"),
            currency="RUB",
            status="succeeded",
            created_at=now,
        ),
    )

    body = PaymentRefundRequest(amount=Decimal("500.00"))
    response = await unwrap(refund_payment)(
        payment_id=1,
        body=body,
        current_user=admin_user,
        _=admin_user,
        session=AsyncMock(),
        commiter=AsyncMock(),
        redis_service=AsyncMock(),
        order_repository=AsyncMock(),
        payment_repository=AsyncMock(),
        refund_repository=AsyncMock(),
        payment_service=service,
        payment_provider_service=AsyncMock(),
        payment_cache_service=AsyncMock(),
        order_cache_service=AsyncMock(),
    )

    assert response.refund.amount == Decimal("500.00")
    assert response.refund.status == "succeeded"


# ---------------------------------------------------------
# POST /payments/webhook
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_process_payment_webhook_invalid_signature():
    service = AsyncMock()
    service.process_webhook.side_effect = InvalidPaymentWebhookSignatureError

    request = MagicMock()
    request.body = AsyncMock(return_value=b'{"event": "payment.succeeded"}')

    with pytest.raises(HTTPException) as exc:
        await unwrap(process_payment_webhook)(
            request=request,
            session=AsyncMock(),
            commiter=AsyncMock(),
            redis_service=AsyncMock(),
            payment_webhook_service=service,
            payment_provider_service=AsyncMock(),
            payment_cache_service=AsyncMock(),
            order_cache_service=AsyncMock(),
            profile_cache_service=AsyncMock(),
            payment_repository=AsyncMock(),
            order_repository=AsyncMock(),
            payment_webhook_log_repository=AsyncMock(),
            notification_service=AsyncMock(),
            email_service=AsyncMock(),
            telegram_service=AsyncMock(),
            one_c_integration_service=AsyncMock(),
        )
    assert exc.value.status_code == 401
    assert "подпись" in exc.value.detail.lower()
