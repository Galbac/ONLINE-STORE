import hashlib
import json
import urllib.parse
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from source.api.api_v1.views.payments import process_payment_webhook
from source.config.settings import settings
from source.errors.auth import InvalidPaymentWebhookPayloadError, InvalidPaymentWebhookSignatureError
from source.services.payment import PaymentProviderService
from source.services.payment_webhook import PaymentWebhookService
from source.tests.unit.services.test_payment_service import (
    build_order, build_payment, build_webhook_body, execute_webhook,
    FakePaymentRepository, FakeOrderRepository, FakePaymentWebhookLogRepository,
)


def robo_body(**overrides):
    params = {"OutSum": "2650.000000", "InvId": "500", "Shp_payment_id": "500", "Shp_order_number": "ORD-TEST"}
    params.update(overrides)
    source = f"{params['OutSum']}:{params['InvId']}:password2"
    source += "".join(f":{key}={params[key]}" for key in sorted(params) if key.startswith("Shp_"))
    params["SignatureValue"] = hashlib.new(settings.payments.robokassa_hash_algorithm, source.encode()).hexdigest()
    return urllib.parse.urlencode(params).encode()


@pytest.mark.parametrize("algorithm", ["md5", "sha256", "sha512"])
def test_result_signature_algorithms(monkeypatch, algorithm):
    monkeypatch.setattr(settings.payments, "robokassa_hash_algorithm", algorithm)
    assert PaymentProviderService().verify_webhook_signature(raw_body=robo_body(), signature=None, robokassa_password_2="password2")


@pytest.mark.parametrize("suffix", [b"&OutSum=1", b"&InvId=9", b"&Shp_payment_id=9", b"&SignatureValue=bad"])
def test_duplicate_form_fields_rejected(suffix):
    with pytest.raises(InvalidPaymentWebhookPayloadError):
        PaymentProviderService().parse_webhook_event(raw_body=robo_body() + suffix)


def test_signed_invoice_must_match_payment_id():
    with pytest.raises(InvalidPaymentWebhookPayloadError):
        PaymentProviderService().parse_webhook_event(raw_body=robo_body(InvId="501"))


@pytest.mark.parametrize("body", [b'{"event":"payment.succeeded","event":"payment.canceled","object":{}}', b'{"event":"payment.succeeded","object":{"id":"p","metadata":[]}}', b"\xff"])
def test_malformed_json_rejected(body):
    with pytest.raises(InvalidPaymentWebhookPayloadError):
        PaymentProviderService().parse_webhook_event(raw_body=body)


@pytest.mark.asyncio
async def test_provider_and_metadata_must_match_local_payment():
    payment = build_payment()
    payment.provider = "robokassa"
    with pytest.raises(InvalidPaymentWebhookPayloadError):
        await execute_webhook(payment=payment)
    payment = build_payment()
    payment.id = 501
    with pytest.raises(InvalidPaymentWebhookPayloadError):
        await execute_webhook(payment=payment)


@pytest.mark.asyncio
async def test_late_cancel_does_not_downgrade_paid_order():
    result = await execute_webhook(body=build_webhook_body(event="payment.canceled"), order=build_order(payment_status="paid"))
    assert result.order_repository.updated_payment_status is None


@pytest.mark.asyncio
async def test_waiting_for_capture_is_not_payment_success():
    body = json.loads(build_webhook_body(event="payment.waiting_for_capture"))
    body["object"]["status"] = "waiting_for_capture"
    result = await execute_webhook(body=json.dumps(body).encode())
    assert result.payment_repository.updated_status == "waiting_for_capture"
    assert result.notification_service.payment_success == []


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_robokassa_verified_payment_and_legacy_links(monkeypatch, legacy):
    monkeypatch.setattr(settings.payments, "robokassa_password_2", "password2")
    payment = build_payment()
    payment.provider = "robokassa"
    payment.provider_payment_id = "robokassa-ORD-TEST" if legacy else "robokassa-500"
    order = build_order()
    order.order_number = "ORD-TEST"
    repo = FakePaymentRepository(payment=payment)
    await PaymentWebhookService().process_webhook(
        raw_body=robo_body(), signature=None, session=AsyncMock(), commiter=AsyncMock(), redis_service=None,
        payment_provider_service=PaymentProviderService(), payment_repository=repo,
        payment_webhook_log_repository=FakePaymentWebhookLogRepository(), order_repository=FakeOrderRepository(order),
        payment_cache_service=AsyncMock(), order_cache_service=AsyncMock(), profile_cache_service=AsyncMock(),
        notification_service=AsyncMock(), email_service=None, telegram_service=None, one_c_integration_service=AsyncMock(),
    )
    assert repo.updated_status == "paid"


async def route_request(method, body):
    sent = False
    async def receive():
        nonlocal sent
        assert not sent
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}
    request = Request({"type": "http", "method": method, "headers": [], "query_string": body if method == "GET" else b""}, receive)
    service = AsyncMock()
    original = getattr(process_payment_webhook, "__dishka_orig_func__", process_payment_webhook)
    response = await original(request=request, payment_webhook_service=service, payment_provider_service=PaymentProviderService())
    return response, service


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_result_url_acknowledges_invoice(method):
    response, service = await route_request(method, robo_body())
    assert response.body == b"OK500"
    service.process_webhook.assert_awaited_once()


@pytest.mark.asyncio
async def test_oversized_webhook_rejected_before_service(monkeypatch):
    monkeypatch.setattr(settings.payments, "webhook_max_body_bytes", 1024)
    with pytest.raises(HTTPException) as error:
        await route_request("POST", b"x" * 1025)
    assert error.value.status_code == 413


@pytest.mark.asyncio
async def test_bad_signature_cannot_mark_payment_paid(monkeypatch):
    monkeypatch.setattr(settings.payments, "robokassa_password_2", "other-password")
    repo = AsyncMock()
    with pytest.raises(InvalidPaymentWebhookSignatureError):
        await PaymentWebhookService().process_webhook(
            raw_body=robo_body(), signature=None, session=AsyncMock(), commiter=AsyncMock(), redis_service=None,
            payment_provider_service=PaymentProviderService(), payment_repository=repo,
            payment_webhook_log_repository=AsyncMock(), order_repository=AsyncMock(),
            payment_cache_service=AsyncMock(), order_cache_service=AsyncMock(), profile_cache_service=AsyncMock(),
            notification_service=AsyncMock(), email_service=None, telegram_service=None, one_c_integration_service=AsyncMock(),
        )
    repo.update_status.assert_not_awaited()
