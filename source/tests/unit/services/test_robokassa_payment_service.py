from decimal import Decimal
import hashlib
import json
import urllib.parse
import pytest

from source.config.settings import settings
from source.errors.auth import PaymentProviderCreateError
from source.services.payment import PaymentProviderService, PaymentService, ProviderPayment


@pytest.mark.asyncio
async def test_robokassa_create_payment_success():
    service = PaymentProviderService()
    payment = await service.create_payment(
        amount=Decimal("1500.50"),
        currency="RUB",
        order_number="ORD-000999",
        description="Оплата заказа ORD-000999",
        return_url="https://site.ru/payment/success",
        webhook_url="https://api.site.ru/api/payments/webhook",
        customer_email="user@example.com",
        provider="robokassa",
        robokassa_login="demo_merchant",
        robokassa_password_1="secret_pass_1",
        robokassa_is_test=True,
        payment_id=777,
    )

    assert isinstance(payment, ProviderPayment)
    assert payment.provider_payment_id == "robokassa-ORD-000999"
    assert payment.status == "pending"
    assert payment.payment_url.startswith("https://auth.robokassa.ru/Merchant/Index.aspx?")

    # Парсим URL и проверяем параметры
    parsed = urllib.parse.urlparse(payment.payment_url)
    qs = urllib.parse.parse_qs(parsed.query)

    assert qs["MerchantLogin"] == ["demo_merchant"]
    assert qs["OutSum"] == ["1500.50"]
    assert qs["InvId"] == ["0"]
    assert qs["Description"] == ["Оплата заказа ORD-000999"]
    assert qs["IsTest"] == ["1"]
    assert qs["Email"] == ["user@example.com"]
    assert qs["Shp_order_number"] == ["ORD-000999"]
    assert qs["Shp_payment_id"] == ["777"]

    # Проверяем контрольную сумму MD5
    # Формат: MerchantLogin:OutSum:InvId:Password#1:Shp_order_number=...:Shp_payment_id=...
    expected_src = "demo_merchant:1500.50:0:secret_pass_1:Shp_order_number=ORD-000999:Shp_payment_id=777"
    expected_sign = hashlib.md5(expected_src.encode("utf-8")).hexdigest()
    assert qs["SignatureValue"] == [expected_sign]


@pytest.mark.asyncio
async def test_robokassa_create_payment_missing_credentials_raises_error():
    service = PaymentProviderService()
    with pytest.raises(PaymentProviderCreateError):
        await service.create_payment(
            amount=Decimal("100.00"),
            currency="RUB",
            order_number="ORD-0001",
            description="Оплата",
            return_url="https://site.ru/success",
            webhook_url="https://site.ru/webhook",
            provider="robokassa",
            robokassa_login="",
            robokassa_password_1="",
        )


def test_robokassa_verify_webhook_signature_and_parse():
    service = PaymentProviderService()

    out_sum = "1500.50"
    inv_id = "0"
    pwd2 = "secret_pass_2"
    shp_order_num = "ORD-000999"
    shp_payment_id = "777"

    # Подпись для ResultURL: OutSum:InvId:Password#2:Shp_order_number=...:Shp_payment_id=...
    sign_src = f"{out_sum}:{inv_id}:{pwd2}:Shp_order_number={shp_order_num}:Shp_payment_id={shp_payment_id}"
    signature = hashlib.md5(sign_src.encode("utf-8")).hexdigest()

    raw_body = f"OutSum={out_sum}&InvId={inv_id}&SignatureValue={signature}&Shp_order_number={shp_order_num}&Shp_payment_id={shp_payment_id}".encode("utf-8")

    # Проверка верификации подписи
    is_valid = service.verify_webhook_signature(
        raw_body=raw_body,
        signature=None,
        robokassa_password_2=pwd2,
    )
    assert is_valid is True

    # Проверка с неверным паролем
    assert service.verify_webhook_signature(
        raw_body=raw_body,
        signature=None,
        robokassa_password_2="wrong_pass",
    ) is False

    # Проверка парсинга вебхука
    event = service.parse_webhook_event(raw_body=raw_body)
    assert event.event_type == "payment.succeeded"
    assert event.provider_payment_id == f"robokassa-{shp_order_num}"
    assert event.payment_id == 777
    assert event.status == "succeeded"
