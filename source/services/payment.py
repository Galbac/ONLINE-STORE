from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
import hashlib
import hmac
import json
import urllib.parse
import urllib.request
import asyncio
import base64
from uuid import uuid5, NAMESPACE_URL
from source.repositories.settings import SettingsRepository

from source.config.settings import settings
from source.errors.auth import (
    InactiveUserError,
    PaymentAlreadyPaidError,
    PaymentAlreadyConfirmedError,
    PaymentAccessDeniedError,
    PaymentCancellationStatusNotAllowedError,
    PaymentConfirmationNotSupportedError,
    PaymentConfirmationStatusNotAllowedError,
    PaymentNotFoundError,
    PaymentProviderConfirmError,
    PaymentProviderCancelError,
    PaymentProviderRefundError,
    PaymentProviderCreateError,
    PaymentNotPaidError,
    InvalidRefundAmountError,
    RefundAmountExceedsAvailableError,
    InvalidPaymentWebhookPayloadError,
)
from source.schemas.pydantic.payment import (
    PaymentCancelPaymentResponse,
    PaymentCancelResponse,
    PaymentConfirmResponse,
    PaymentCreateResponse,
    PaymentDetailResponse,
    PaymentRefundResponse,
    RefundResponse,
)


@dataclass(slots=True)
class ProviderPayment:
    provider_payment_id: str
    payment_url: str | None
    status: str


@dataclass(slots=True)
class ProviderPaymentStatus:
    status: str
    paid_at: object | None = None


@dataclass(slots=True)
class ProviderWebhookEvent:
    provider_event_id: str
    event_type: str
    provider_payment_id: str | None
    payment_id: int | None
    status: str | None
    payload: dict


@dataclass(slots=True)
class ProviderRefund:
    provider_refund_id: str
    status: str


class PaymentProviderService:
    async def request_yookassa(
        self,
        *,
        method,
        path,
        data=None,
        session=None,
        shop_id=None,
        secret_key=None,
        operation_key=None,
    ):
        if session is not None:
            configured = await SettingsRepository().get(session=session)
            if configured:
                shop_id = shop_id or configured.yookassa_shop_id
                secret_key = secret_key or configured.yookassa_secret_key
        shop_id = shop_id or settings.payments.provider_shop_id
        secret_key = secret_key or settings.payments.provider_secret_key
        if not shop_id or not secret_key:
            raise PaymentProviderCreateError

        def send():
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic "
                + base64.b64encode(f"{shop_id}:{secret_key}".encode()).decode(),
            }
            if method != "GET":
                headers["Idempotence-Key"] = str(
                    uuid5(
                        NAMESPACE_URL,
                        operation_key or path + json.dumps(data, sort_keys=True),
                    )
                )
            request = urllib.request.Request(
                "https://api.yookassa.ru/v3/" + path,
                data=json.dumps(data).encode() if data is not None else None,
                headers=headers,
                method=method,
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise PaymentProviderCreateError
            return result

        try:
            return await asyncio.to_thread(send)
        except Exception as error:
            raise PaymentProviderCreateError from error

    def payment_status(self, data):
        status = {"succeeded": "paid", "canceled": "cancelled"}.get(
            data["status"], data["status"]
        )
        paid_at = (
            datetime.fromisoformat(data["captured_at"].replace("Z", "+00:00"))
            if data.get("captured_at")
            else None
        )
        return ProviderPaymentStatus(status=status, paid_at=paid_at)

    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        order_number: str,
        description: str,
        return_url: str,
        webhook_url: str,
        customer_email: str | None = None,
        provider: str | None = None,
        robokassa_login: str | None = None,
        robokassa_password_1: str | None = None,
        robokassa_is_test: bool = False,
        yookassa_shop_id: str | None = None,
        yookassa_secret_key: str | None = None,
        payment_id: int | None = None,
    ) -> ProviderPayment:
        selected_provider = (
            provider or settings.payments.provider or "yookassa"
        ).lower()
        if selected_provider not in ("yookassa", "robokassa"):
            raise PaymentProviderCreateError

        if selected_provider == "robokassa":
            merchant_login = (
                robokassa_login or settings.payments.robokassa_merchant_login
            )
            password_1 = robokassa_password_1 or settings.payments.robokassa_password_1
            if not merchant_login or not password_1:
                raise PaymentProviderCreateError

            out_sum = f"{amount:.2f}"
            inv_id = (
                payment_id
                if payment_id is not None
                else int(order_number) if str(order_number).isdigit() else 0
            )

            shp_params: dict[str, str] = {"Shp_order_number": str(order_number)}
            if payment_id is not None:
                shp_params["Shp_payment_id"] = str(payment_id)

            sorted_shp = sorted(shp_params.items(), key=lambda x: x[0])
            shp_signature_part = ":".join(f"{k}={v}" for k, v in sorted_shp)
            signature_source = f"{merchant_login}:{out_sum}:{inv_id}:{password_1}"
            if shp_signature_part:
                signature_source = f"{signature_source}:{shp_signature_part}"
            signature_value = hashlib.md5(signature_source.encode("utf-8")).hexdigest()

            query_params: dict[str, str] = {
                "MerchantLogin": merchant_login,
                "OutSum": out_sum,
                "InvId": str(inv_id),
                "Description": description,
                "SignatureValue": signature_value,
            }
            if robokassa_is_test or settings.payments.robokassa_is_test:
                query_params["IsTest"] = "1"
            if customer_email:
                query_params["Email"] = customer_email
            for k, v in sorted_shp:
                query_params[k] = v

            payment_url = f"https://auth.robokassa.ru/Merchant/Index.aspx?{urllib.parse.urlencode(query_params)}"
            return ProviderPayment(
                provider_payment_id=f"robokassa-{order_number}",
                payment_url=payment_url,
                status="pending",
            )

        data = await self.request_yookassa(
            method="POST",
            path="payments",
            shop_id=yookassa_shop_id,
            secret_key=yookassa_secret_key,
            operation_key=f"payment:{order_number}:{payment_id}",
            data={
                "amount": {"value": f"{amount:.2f}", "currency": currency},
                "capture": settings.payments.capture_mode != "manual",
                "confirmation": {"type": "redirect", "return_url": return_url},
                "description": description[:128],
                "metadata": {
                    "payment_id": str(payment_id),
                    "order_number": order_number,
                },
            },
        )
        return ProviderPayment(
            provider_payment_id=data["id"],
            payment_url=data.get("confirmation", {}).get("confirmation_url"),
            status=self.payment_status(data).status,
        )

    async def get_payment_status(
        self, *, provider_payment_id: str, session=None
    ) -> ProviderPaymentStatus:
        if not provider_payment_id or provider_payment_id.startswith("robokassa-"):
            raise PaymentProviderConfirmError
        data = await self.request_yookassa(
            method="GET",
            path="payments/" + urllib.parse.quote(provider_payment_id, safe=""),
            session=session,
        )
        return self.payment_status(data)

    async def confirm_payment(
        self,
        *,
        provider_payment_id: str,
        amount: Decimal | None = None,
        session=None,
        currency=None,
    ) -> ProviderPaymentStatus:
        if settings.payments.capture_mode != "manual":
            raise PaymentConfirmationNotSupportedError
        if not provider_payment_id or provider_payment_id.startswith("robokassa-"):
            raise PaymentProviderConfirmError
        try:
            data = await self.request_yookassa(
                method="POST",
                path=f"payments/{urllib.parse.quote(provider_payment_id, safe='')}/capture",
                session=session,
                data=(
                    {
                        "amount": {
                            "value": f"{amount:.2f}",
                            "currency": currency or settings.payments.currency,
                        }
                    }
                    if amount is not None
                    else {}
                ),
            )
            return self.payment_status(data)
        except PaymentProviderCreateError as error:
            raise PaymentProviderConfirmError from error

    async def cancel_payment(
        self, *, provider_payment_id: str, reason: str | None = None, session=None
    ) -> ProviderPaymentStatus:
        if not provider_payment_id or provider_payment_id.startswith("robokassa-"):
            raise PaymentProviderCancelError
        try:
            data = await self.request_yookassa(
                method="POST",
                path=f"payments/{urllib.parse.quote(provider_payment_id, safe='')}/cancel",
                data={},
                session=session,
            )
            return self.payment_status(data)
        except PaymentProviderCreateError as error:
            raise PaymentProviderCancelError from error

    async def refund_payment(
        self,
        *,
        provider_payment_id: str,
        amount: Decimal,
        reason: str | None = None,
        session=None,
        currency=None,
        operation_key=None,
    ) -> ProviderRefund:
        if not provider_payment_id or provider_payment_id.startswith("robokassa-"):
            raise PaymentProviderRefundError
        try:
            data = await self.request_yookassa(
                method="POST",
                path="refunds",
                session=session,
                operation_key=operation_key,
                data={
                    "payment_id": provider_payment_id,
                    "amount": {
                        "value": f"{amount:.2f}",
                        "currency": currency or settings.payments.currency,
                    },
                    "description": (reason or "Возврат заказа")[:250],
                },
            )
            return ProviderRefund(provider_refund_id=data["id"], status=data["status"])
        except PaymentProviderCreateError as error:
            raise PaymentProviderRefundError from error

    def verify_webhook_signature(
        self,
        *,
        raw_body: bytes,
        signature: str | None,
        robokassa_password_2: str | None = None,
    ) -> bool:
        try:
            raw_str = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            raw_str = ""

        # Robokassa ResultURL signature check
        if "OutSum=" in raw_str or "SignatureValue=" in raw_str:
            params = urllib.parse.parse_qs(raw_str)
            out_sum = params.get("OutSum", [""])[0]
            inv_id = params.get("InvId", [""])[0]
            sig_received = params.get("SignatureValue", [""])[0]
            pwd2 = robokassa_password_2 or settings.payments.robokassa_password_2
            if not pwd2 or not sig_received:
                return False

            shp_params = {k: v[0] for k, v in params.items() if k.startswith("Shp_")}
            sorted_shp = sorted(shp_params.items(), key=lambda x: x[0])
            shp_part = ":".join(f"{k}={v}" for k, v in sorted_shp)
            sign_str = f"{out_sum}:{inv_id}:{pwd2}"
            if shp_part:
                sign_str = f"{sign_str}:{shp_part}"
            expected_sig = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
            return expected_sig.lower() == sig_received.lower()

        # YooKassa signature check
        if not signature or not settings.payments.provider_webhook_secret:
            return False
        expected_signature = hmac.new(
            settings.payments.provider_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected_signature)

    def parse_webhook_event(self, *, raw_body: bytes) -> ProviderWebhookEvent:
        try:
            raw_str = raw_body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InvalidPaymentWebhookPayloadError from error

        # Robokassa ResultURL format
        if "OutSum=" in raw_str or "SignatureValue=" in raw_str:
            params = urllib.parse.parse_qs(raw_str)
            inv_id = params.get("InvId", [None])[0]
            out_sum = params.get("OutSum", [None])[0]
            sig = params.get("SignatureValue", [""])[0]
            shp_payment_id = params.get("Shp_payment_id", [None])[0]
            shp_order_num = params.get("Shp_order_number", [None])[0]

            if not out_sum or not inv_id:
                raise InvalidPaymentWebhookPayloadError

            parsed_payment_id = None
            if shp_payment_id is not None:
                try:
                    parsed_payment_id = int(shp_payment_id)
                except (ValueError, TypeError):
                    pass

            provider_payment_id = f"robokassa-{shp_order_num or inv_id}"
            event_id = f"robokassa:{provider_payment_id}:{sig or out_sum}"

            return ProviderWebhookEvent(
                provider_event_id=str(event_id),
                event_type="payment.succeeded",
                provider_payment_id=provider_payment_id,
                payment_id=parsed_payment_id,
                status="succeeded",
                payload={
                    "InvId": inv_id,
                    "OutSum": out_sum,
                    "SignatureValue": sig,
                    "raw": raw_str,
                },
            )

        # YooKassa JSON format
        try:
            payload = json.loads(raw_str)
        except json.JSONDecodeError as error:
            raise InvalidPaymentWebhookPayloadError from error

        if not isinstance(payload, dict):
            raise InvalidPaymentWebhookPayloadError
        event_type = payload.get("event")
        event_object = payload.get("object")
        if not isinstance(event_type, str) or not isinstance(event_object, dict):
            raise InvalidPaymentWebhookPayloadError

        provider_payment_id = event_object.get("id")
        metadata = event_object.get("metadata") or {}
        payment_id = metadata.get("payment_id")
        try:
            parsed_payment_id = int(payment_id) if payment_id is not None else None
        except (TypeError, ValueError) as error:
            raise InvalidPaymentWebhookPayloadError from error

        provider_event_id = payload.get("id")
        if provider_event_id is None:
            if not provider_payment_id:
                raise InvalidPaymentWebhookPayloadError
            provider_event_id = f"{event_type}:{provider_payment_id}"

        return ProviderWebhookEvent(
            provider_event_id=str(provider_event_id),
            event_type=event_type,
            provider_payment_id=str(
                event_object.get("payment_id")
                if event_type.startswith("refund.")
                else provider_payment_id
            ),
            payment_id=parsed_payment_id,
            status=event_object.get("status"),
            payload=payload,
        )


class PaymentService:
    async def create_payment(
        self,
        *,
        payment_repository,
        session,
        order,
        commiter=None,
        redis_service=None,
        user=None,
        order_repository=None,
        order_service=None,
        payment_provider_service: PaymentProviderService | None = None,
        order_cache_service=None,
        settings_repository=None,
    ):
        provider = settings.payments.provider
        robokassa_login = getattr(settings.payments, "robokassa_merchant_login", None)
        robokassa_pwd1 = getattr(settings.payments, "robokassa_password_1", None)
        robokassa_is_test = getattr(settings.payments, "robokassa_is_test", False)
        yookassa_shop_id = getattr(settings.payments, "provider_shop_id", None)
        yookassa_secret_key = getattr(settings.payments, "provider_secret_key", None)

        if settings_repository is not None and session is not None:
            store_settings, _ = await settings_repository.get_or_create_default(
                session=session
            )
            if store_settings is not None:
                if getattr(store_settings, "payment_provider", None):
                    provider = store_settings.payment_provider
                if getattr(store_settings, "robokassa_merchant_login", None):
                    robokassa_login = store_settings.robokassa_merchant_login
                if getattr(store_settings, "robokassa_password_1", None):
                    robokassa_pwd1 = store_settings.robokassa_password_1
                if hasattr(store_settings, "robokassa_is_test"):
                    robokassa_is_test = bool(store_settings.robokassa_is_test)
                if getattr(store_settings, "yookassa_shop_id", None):
                    yookassa_shop_id = store_settings.yookassa_shop_id
                if getattr(store_settings, "yookassa_secret_key", None):
                    yookassa_secret_key = store_settings.yookassa_secret_key

        if commiter is None:
            await payment_repository.create(
                session=session,
                order_id=order.id,
                amount=order.final_price,
                currency=settings.payments.currency,
                status="unpaid",
                provider=provider,
                payment_url=None,
            )
            return None

        active_payment = None
        try:
            order_service.validate_order_for_payment(order=order, user=user)
            active_payment = await payment_repository.get_active_by_order_id(
                session=session, order_id=order.id
            )
            if (
                active_payment is not None
                and active_payment.provider_payment_id
                and active_payment.payment_url
            ):
                return self._build_response(order=order, payment=active_payment)
            payment = active_payment or await payment_repository.create(
                session=session,
                order_id=order.id,
                amount=order.final_price,
                currency=settings.payments.currency,
                status="pending",
                provider=provider,
                payment_url=None,
            )
            provider_payment = await payment_provider_service.create_payment(
                amount=order.final_price,
                currency=settings.payments.currency,
                order_number=order.order_number,
                description=f"Оплата заказа {order.order_number}",
                return_url=settings.payments.return_url,
                webhook_url=settings.payments.webhook_url,
                customer_email=order.customer_email,
                provider=provider,
                robokassa_login=robokassa_login,
                robokassa_password_1=robokassa_pwd1,
                robokassa_is_test=robokassa_is_test,
                yookassa_shop_id=yookassa_shop_id,
                yookassa_secret_key=yookassa_secret_key,
                payment_id=payment.id,
            )
            payment = await payment_repository.update_provider_data(
                session=session,
                payment=payment,
                provider_payment_id=provider_payment.provider_payment_id,
                payment_url=provider_payment.payment_url,
                status=provider_payment.status,
            )
            if order.payment_status != provider_payment.status:
                await order_repository.update_payment_status(
                    session=session,
                    order=order,
                    payment_status=provider_payment.status,
                )
            await commiter.commit()
        except Exception as error:
            await commiter.rollback()
            if isinstance(error, PaymentProviderCreateError):
                raise
            raise

        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order.id,
        )
        return self._build_response(order=order, payment=payment)

    async def create_refund_request(self, *, order, session, payment) -> None:
        from source.repositories.refund import RefundRepository

        refunded = await RefundRepository().sum_refunded_by_payment_id(
            session=session, payment_id=payment.id
        )
        amount = payment.amount - refunded
        if amount <= 0:
            return
        result = await PaymentProviderService().refund_payment(
            provider_payment_id=payment.provider_payment_id,
            amount=amount,
            currency=payment.currency,
            session=session,
            reason="Отмена заказа",
            operation_key=f"refund:{payment.id}:{refunded}:{amount}",
        )
        await RefundRepository().create(
            session=session,
            payment_id=payment.id,
            amount=amount,
            currency=payment.currency,
            status=result.status,
            reason="Отмена заказа",
            provider_refund_id=result.provider_refund_id,
        )
        payment.refund_status = (
            "refunded" if result.status == "succeeded" else "pending"
        )
        order.payment_status = payment.refund_status
        await session.flush()

    def build_fiscal_receipt_items(self, *, order, order_items) -> list[dict]:
        items = []
        for item in order_items:
            items.append(
                {
                    "name": item.product_name,
                    "quantity": item.quantity,
                    "price": item.price,
                    "total_amount": item.final_price,
                    "payment_subject": 1,
                    "payment_subject_name": "ТОВАР",
                }
            )
        if getattr(order, "delivery_price", Decimal("0")) > Decimal("0"):
            items.append(
                {
                    "name": "Услуга курьерской доставки",
                    "quantity": Decimal("1.0"),
                    "price": order.delivery_price,
                    "total_amount": order.delivery_price,
                    "payment_subject": 4,
                    "payment_subject_name": "УСЛУГА",
                }
            )
        return items

    async def get_payment_detail(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        payment_id: int,
        payment_repository,
        order_repository,
        payment_provider_service: PaymentProviderService,
        payment_cache_service,
        order_cache_service,
    ) -> PaymentDetailResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cached_payment = await payment_cache_service.get_detail(
            redis_service=redis_service,
            user_id=user.id,
            payment_id=payment_id,
        )
        if cached_payment is not None:
            return cached_payment

        payment = await payment_repository.get_by_id(
            session=session, payment_id=payment_id
        )
        if payment is None:
            raise PaymentNotFoundError
        order = await order_repository.get_by_id(
            session=session, order_id=payment.order_id
        )
        if order is None:
            raise PaymentNotFoundError
        if order.user_id != user.id:
            raise PaymentAccessDeniedError

        if (
            settings.payments.status_sync_enabled
            and payment.provider_payment_id
            and payment.provider != "robokassa"
        ):
            provider_status = await payment_provider_service.get_payment_status(
                provider_payment_id=payment.provider_payment_id,
                session=session,
            )
            if provider_status.status != payment.status and payment.status != "paid":
                try:
                    payment = await payment_repository.update_status(
                        session=session,
                        payment=payment,
                        status=provider_status.status,
                        paid_at=provider_status.paid_at,
                    )
                    await order_repository.update_payment_status(
                        session=session,
                        order=order,
                        payment_status=provider_status.status,
                    )
                    await commiter.commit()
                except Exception:
                    await commiter.rollback()
                    raise
                await order_cache_service.invalidate_order(
                    redis_service=redis_service,
                    user_id=user.id,
                    order_id=order.id,
                )

        response = self._build_detail_response(order=order, payment=payment)
        await payment_cache_service.set_detail(
            redis_service=redis_service,
            user_id=user.id,
            payment_id=payment.id,
            response=response,
            ttl_seconds=settings.payments.detail_cache_ttl_seconds,
        )
        return response

    async def confirm_payment(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        payment_id: int,
        amount: Decimal | None,
        payment_repository,
        order_repository,
        payment_provider_service: PaymentProviderService,
        payment_cache_service,
        order_cache_service,
    ) -> PaymentConfirmResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        payment = await payment_repository.get_by_id(
            session=session, payment_id=payment_id
        )
        if payment is None:
            raise PaymentNotFoundError
        order = await order_repository.get_by_id(
            session=session, order_id=payment.order_id
        )
        if order is None:
            raise PaymentNotFoundError
        if order.user_id != user.id:
            raise PaymentAccessDeniedError
        if payment.status == "paid":
            raise PaymentAlreadyConfirmedError
        if payment.status not in {"waiting_for_capture", "authorized"}:
            raise PaymentConfirmationStatusNotAllowedError
        if settings.payments.capture_mode != "manual":
            raise PaymentConfirmationNotSupportedError

        try:
            provider_status = await payment_provider_service.confirm_payment(
                provider_payment_id=payment.provider_payment_id,
                session=session,
                amount=amount,
                currency=payment.currency,
            )
            normalized_status = (
                "paid"
                if provider_status.status in {"paid", "succeeded"}
                else provider_status.status
            )
            payment = await payment_repository.update_status(
                session=session,
                payment=payment,
                status=normalized_status,
                paid_at=provider_status.paid_at,
            )
            if normalized_status == "paid":
                await order_repository.update_payment_status(
                    session=session,
                    order=order,
                    payment_status="paid",
                )
                if order.status == "pending_payment":
                    await order_repository.update_status(
                        session=session,
                        order=order,
                        status="new",
                    )
            await commiter.commit()
        except (
            PaymentConfirmationNotSupportedError,
            PaymentProviderConfirmError,
        ):
            await commiter.rollback()
            raise
        except Exception:
            await commiter.rollback()
            raise

        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order.id,
        )
        await payment_cache_service.invalidate_detail(
            redis_service=redis_service,
            user_id=user.id,
            payment_id=payment.id,
        )
        return PaymentConfirmResponse(
            id=payment.id,
            order_id=order.id,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            paid_at=payment.paid_at,
        )

    async def cancel_payment(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        payment_id: int,
        reason: str | None,
        payment_repository,
        order_repository,
        payment_provider_service: PaymentProviderService,
        payment_cache_service,
        order_cache_service,
    ) -> PaymentCancelResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        payment = await payment_repository.get_by_id(
            session=session, payment_id=payment_id
        )
        if payment is None:
            raise PaymentNotFoundError
        order = await order_repository.get_by_id(
            session=session, order_id=payment.order_id
        )
        if order is None:
            raise PaymentNotFoundError
        if order.user_id != user.id:
            raise PaymentAccessDeniedError
        if payment.status == "paid":
            raise PaymentAlreadyPaidError
        if payment.status not in {"pending", "waiting_for_capture", "authorized"}:
            raise PaymentCancellationStatusNotAllowedError

        try:
            provider_status = await payment_provider_service.cancel_payment(
                provider_payment_id=payment.provider_payment_id,
                session=session,
                reason=reason,
            )
            payment = await payment_repository.update_status(
                session=session,
                payment=payment,
                status=provider_status.status,
                cancelled_at=datetime.now(settings.tz),
            )
            await order_repository.update_payment_status(
                session=session,
                order=order,
                payment_status="unpaid",
            )
            await commiter.commit()
        except PaymentProviderCancelError:
            await commiter.rollback()
            raise
        except Exception:
            await commiter.rollback()
            raise

        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order.id,
        )
        await payment_cache_service.invalidate_detail(
            redis_service=redis_service,
            user_id=user.id,
            payment_id=payment.id,
        )
        return PaymentCancelResponse(
            message="Платёж отменён",
            payment=PaymentCancelPaymentResponse(
                id=payment.id,
                order_id=order.id,
                status=payment.status,
                amount=payment.amount,
                currency=payment.currency,
                cancelled_at=payment.cancelled_at,
            ),
        )

    async def refund_payment(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        payment_id: int,
        amount: Decimal | None,
        reason: str | None,
        payment_repository,
        refund_repository,
        order_repository,
        payment_provider_service: PaymentProviderService,
        payment_cache_service,
        order_cache_service,
        notification_service,
        email_service,
        telegram_service,
        notification_repository=None,
        web_push_service=None,
        push_subscription_repository=None,
    ) -> PaymentRefundResponse:
        payment = await payment_repository.get_by_id(
            session=session, payment_id=payment_id
        )
        if payment is None:
            raise PaymentNotFoundError
        if payment.status != "paid":
            raise PaymentNotPaidError
        order = await order_repository.get_by_id(
            session=session, order_id=payment.order_id
        )
        if order is None:
            raise PaymentNotFoundError

        already_refunded = await refund_repository.sum_refunded_by_payment_id(
            session=session,
            payment_id=payment.id,
        )
        available_amount = payment.amount - already_refunded
        refund_amount = available_amount if amount is None else amount
        if refund_amount <= 0:
            raise InvalidRefundAmountError
        if refund_amount > available_amount:
            raise RefundAmountExceedsAvailableError

        try:
            provider_refund = await payment_provider_service.refund_payment(
                provider_payment_id=payment.provider_payment_id,
                session=session,
                amount=refund_amount,
                currency=payment.currency,
                operation_key=f"refund:{payment.id}:{already_refunded}:{refund_amount}",
                reason=reason,
            )
            refund = await refund_repository.create(
                session=session,
                payment_id=payment.id,
                amount=refund_amount,
                currency=payment.currency,
                status=provider_refund.status,
                reason=reason,
                provider_refund_id=provider_refund.provider_refund_id,
            )
            succeeded_amount = await refund_repository.sum_succeeded_by_payment_id(
                session=session, payment_id=payment.id,
            )
            is_full_refund = succeeded_amount >= payment.amount
            refund_status = (
                ("refunded" if is_full_refund else "partial_refunded")
                if provider_refund.status == "succeeded"
                else "pending"
            )
            await payment_repository.update_refund_status(
                session=session,
                payment=payment,
                refund_status=refund_status,
            )
            await order_repository.update_payment_status(
                session=session,
                order=order,
                payment_status=refund_status,
            )
            await commiter.commit()
        except PaymentProviderRefundError:
            await commiter.rollback()
            raise
        except Exception:
            await commiter.rollback()
            raise

        await payment_cache_service.invalidate_detail(
            redis_service=redis_service,
            user_id=order.user_id,
            payment_id=payment.id,
        )
        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=order.user_id,
            order_id=order.id,
        )
        await notification_service.notify_refund_created(
            email_service=email_service,
            telegram_service=telegram_service,
            order=order,
            session=session,
            notification_repository=notification_repository,
            web_push_service=web_push_service,
            push_subscription_repository=push_subscription_repository,
        )
        if notification_repository is not None:
            await commiter.commit()
        return PaymentRefundResponse(
            message="Возврат создан",
            refund=RefundResponse(
                id=refund.id,
                payment_id=payment.id,
                order_id=order.id,
                amount=refund.amount,
                currency=refund.currency,
                status=refund.status,
                reason=refund.reason,
                created_at=refund.created_date,
            ),
        )

    def _build_response(self, *, order, payment) -> PaymentCreateResponse:
        return PaymentCreateResponse(
            id=payment.id,
            order_id=order.id,
            order_number=order.order_number,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            provider=payment.provider or settings.payments.provider,
            payment_url=payment.payment_url,
            created_at=payment.created_date,
        )

    def _build_detail_response(self, *, order, payment) -> PaymentDetailResponse:
        return PaymentDetailResponse(
            id=payment.id,
            order_id=order.id,
            order_number=order.order_number,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            provider=payment.provider or settings.payments.provider,
            payment_url=payment.payment_url,
            paid_at=payment.paid_at,
            created_at=payment.created_date,
            updated_at=payment.updated_date,
        )
