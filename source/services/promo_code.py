from datetime import datetime
from decimal import Decimal

from source.config.settings import settings
from source.errors.auth import (
    CartPromoCodeAlreadyAppliedError,
    CartPromoCodeExpiredError,
    CartPromoCodeInactiveError,
    CartPromoCodeLimitExceededError,
    CartPromoCodeMinAmountError,
    CartPromoCodeNotApplicableError,
    CartPromoCodeNotFoundError,
)
from source.schemas.pydantic.promo_code import PromoCodeCheckRequest, PromoCodeCheckResponse
from source.utils.promo_code import calculate_promo_discount


class PromoCodeService:
    async def check_promo_code(
        self,
        *,
        session,
        promo_code_repository,
        promo_code_usage_repository,
        user_id: int | None,
        data: PromoCodeCheckRequest,
    ) -> PromoCodeCheckResponse:
        promo_code = await promo_code_repository.get_by_code(session=session, code=data.code)
        if promo_code is None:
            raise CartPromoCodeNotFoundError

        now = datetime.now(settings.tz)
        if not promo_code.is_active or (promo_code.starts_at is not None and promo_code.starts_at > now):
            raise CartPromoCodeInactiveError
        if promo_code.ends_at is not None and promo_code.ends_at < now:
            raise CartPromoCodeExpiredError

        total_usage_count = await promo_code_usage_repository.count_by_code(session=session, promo_code_id=promo_code.id)
        if promo_code.usage_limit is not None and total_usage_count >= promo_code.usage_limit:
            raise CartPromoCodeLimitExceededError
        if user_id is not None and promo_code.per_user_usage_limit is not None:
            user_usage_count = await promo_code_usage_repository.count_by_user_and_code(
                session=session,
                user_id=user_id,
                promo_code_id=promo_code.id,
            )
            if user_usage_count >= promo_code.per_user_usage_limit:
                raise CartPromoCodeLimitExceededError

        if (
            data.cart_total is not None
            and promo_code.min_order_amount is not None
            and data.cart_total < promo_code.min_order_amount
        ):
            return PromoCodeCheckResponse(
                valid=False,
                code=promo_code.code,
                min_order_amount=promo_code.min_order_amount,
                amount_left=promo_code.min_order_amount - data.cart_total,
                message="Сумма заказа меньше минимальной суммы для промокода",
            )

        return PromoCodeCheckResponse(
            valid=True,
            code=promo_code.code,
            discount_type=promo_code.discount_type,
            discount_value=promo_code.discount_value,
            discount_amount=self.calculate_preview_discount(promo_code=promo_code, cart_total=data.cart_total),
            min_order_amount=promo_code.min_order_amount,
            message="Промокод доступен",
        )

    def calculate_preview_discount(self, *, promo_code, cart_total: Decimal | None) -> Decimal | None:
        if cart_total is None:
            return None
        return calculate_promo_discount(
            discount_type=promo_code.discount_type,
            discount_value=promo_code.discount_value,
            amount=cart_total,
        )

    def validate_for_cart(
        self,
        **kwargs,
    ) -> None:
        return self.validate_promo_code(**kwargs)

    def validate_promo_code(
        self,
        *,
        promo_code,
        cart,
        cart_items: list,
        products_by_id: dict,
        subtotal: Decimal,
        total_usage_count: int,
        user_usage_count: int,
    ) -> None:
        now = datetime.now(settings.tz)
        if cart.promo_code_id == promo_code.id:
            raise CartPromoCodeAlreadyAppliedError
        if not promo_code.is_active or (promo_code.starts_at is not None and promo_code.starts_at > now):
            raise CartPromoCodeInactiveError
        if promo_code.ends_at is not None and promo_code.ends_at < now:
            raise CartPromoCodeExpiredError
        if promo_code.usage_limit is not None and total_usage_count >= promo_code.usage_limit:
            raise CartPromoCodeLimitExceededError
        if promo_code.per_user_usage_limit is not None and user_usage_count >= promo_code.per_user_usage_limit:
            raise CartPromoCodeLimitExceededError
        if promo_code.min_order_amount is not None and subtotal < promo_code.min_order_amount:
            raise CartPromoCodeMinAmountError
        if promo_code.applicable_product_id is not None and not any(
            item.product_id == promo_code.applicable_product_id
            for item in cart_items
        ):
            raise CartPromoCodeNotApplicableError
        if promo_code.applicable_category_id is not None and not any(
            products_by_id.get(item.product_id) is not None
            and products_by_id[item.product_id].category_id == promo_code.applicable_category_id
            for item in cart_items
        ):
            raise CartPromoCodeNotApplicableError
        if not promo_code.allow_discounted_products and any(
            products_by_id.get(item.product_id) is not None
            and products_by_id[item.product_id].old_price is not None
            and products_by_id[item.product_id].old_price > products_by_id[item.product_id].price
            for item in cart_items
        ):
            raise CartPromoCodeNotApplicableError

    def calculate_discount(self, *, promo_code, amount: Decimal) -> Decimal:
        if promo_code.discount_type == "percent":
            return amount * promo_code.discount_value / Decimal("100")
        return min(promo_code.discount_value, amount)

    def validate_for_order(
        self,
        *,
        promo_code,
        cart,
        cart_items: list,
        products_by_id: dict,
        subtotal: Decimal,
        total_usage_count: int,
        user_usage_count: int,
    ) -> None:
        now = datetime.now(settings.tz)
        if not promo_code.is_active or (promo_code.starts_at is not None and promo_code.starts_at > now):
            raise CartPromoCodeInactiveError
        if promo_code.ends_at is not None and promo_code.ends_at < now:
            raise CartPromoCodeExpiredError
        if promo_code.usage_limit is not None and total_usage_count >= promo_code.usage_limit:
            raise CartPromoCodeLimitExceededError
        if promo_code.per_user_usage_limit is not None and user_usage_count >= promo_code.per_user_usage_limit:
            raise CartPromoCodeLimitExceededError
        if promo_code.min_order_amount is not None and subtotal < promo_code.min_order_amount:
            raise CartPromoCodeMinAmountError
        if promo_code.applicable_product_id is not None and not any(
            item.product_id == promo_code.applicable_product_id
            for item in cart_items
        ):
            raise CartPromoCodeNotApplicableError
        if promo_code.applicable_category_id is not None and not any(
            products_by_id.get(item.product_id) is not None
            and products_by_id[item.product_id].category_id == promo_code.applicable_category_id
            for item in cart_items
        ):
            raise CartPromoCodeNotApplicableError
        if not promo_code.allow_discounted_products and any(
            products_by_id.get(item.product_id) is not None
            and products_by_id[item.product_id].old_price is not None
            and products_by_id[item.product_id].old_price > products_by_id[item.product_id].price
            for item in cart_items
        ):
            raise CartPromoCodeNotApplicableError

    async def reserve_usage(
        self,
        *,
        promo_code_usage_repository,
        session,
        promo_code_id: int,
        user_id: int,
        order_id: int | None = None,
    ):
        return await promo_code_usage_repository.create(
            session=session,
            promo_code_id=promo_code_id,
            user_id=user_id,
            order_id=order_id,
            status="reserved",
        )

    async def cancel_usage(self, *, promo_code_usage_repository, session, order_id: int) -> None:
        await promo_code_usage_repository.cancel_by_order_id(session=session, order_id=order_id)
