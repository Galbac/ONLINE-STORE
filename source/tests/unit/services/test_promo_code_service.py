from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.errors.auth import CartPromoCodeExpiredError, CartPromoCodeInactiveError, CartPromoCodeLimitExceededError, CartPromoCodeNotFoundError
from source.schemas.pydantic.promo_code import PromoCodeCheckRequest
from source.services.promo_code import PromoCodeService


_DEFAULT = object()


class FakePromoCodeRepository:
    def __init__(self, promo_code=_DEFAULT) -> None:
        self.promo_code = build_promo_code() if promo_code is _DEFAULT else promo_code

    async def get_by_code(self, *, session, code: str):
        return self.promo_code if self.promo_code is not None and self.promo_code.code == code else None


class FakePromoCodeUsageRepository:
    def __init__(self, total_count: int = 0, user_count: int = 0) -> None:
        self.total_count = total_count
        self.user_count = user_count
        self.created = False

    async def count_by_code(self, *, session, promo_code_id: int) -> int:
        return self.total_count

    async def count_by_user_and_code(self, *, session, user_id: int, promo_code_id: int) -> int:
        return self.user_count

    async def create(self, **kwargs):
        self.created = True


def build_promo_code(
    *,
    is_active: bool = True,
    starts_at=None,
    ends_at=None,
    min_order_amount: Decimal | None = Decimal("1000.00"),
    usage_limit: int | None = None,
    per_user_usage_limit: int | None = None,
):
    return SimpleNamespace(
        id=1,
        code="PROMO10",
        discount_type="percent",
        discount_value=Decimal("10"),
        min_order_amount=min_order_amount,
        usage_limit=usage_limit,
        per_user_usage_limit=per_user_usage_limit,
        is_active=is_active,
        starts_at=starts_at,
        ends_at=ends_at,
    )


async def execute_check(*, promo_code=_DEFAULT, usage_repository=None, user_id: int | None = 1, cart_total=Decimal("2500.00")):
    return await PromoCodeService().check_promo_code(
        session=object(),
        promo_code_repository=FakePromoCodeRepository(promo_code),
        promo_code_usage_repository=usage_repository or FakePromoCodeUsageRepository(),
        user_id=user_id,
        data=PromoCodeCheckRequest(code=" promo10 ", cart_total=cart_total),
    )


@pytest.mark.asyncio
async def test_check_promo_code_valid() -> None:
    response = await execute_check()

    assert response.valid is True
    assert response.code == "PROMO10"
    assert response.discount_amount == Decimal("250.00")


@pytest.mark.asyncio
async def test_check_promo_code_not_found() -> None:
    with pytest.raises(CartPromoCodeNotFoundError):
        await execute_check(promo_code=None, user_id=None)


@pytest.mark.asyncio
async def test_check_promo_code_inactive() -> None:
    with pytest.raises(CartPromoCodeInactiveError):
        await execute_check(promo_code=build_promo_code(is_active=False))


@pytest.mark.asyncio
async def test_check_promo_code_expired() -> None:
    with pytest.raises(CartPromoCodeExpiredError):
        await execute_check(promo_code=build_promo_code(ends_at=datetime.now(settings.tz) - timedelta(days=1)))


@pytest.mark.asyncio
async def test_check_promo_code_not_started() -> None:
    with pytest.raises(CartPromoCodeInactiveError):
        await execute_check(promo_code=build_promo_code(starts_at=datetime.now(settings.tz) + timedelta(days=1)))


@pytest.mark.asyncio
async def test_check_promo_code_min_amount_invalid_response() -> None:
    response = await execute_check(cart_total=Decimal("500.00"))

    assert response.valid is False
    assert response.amount_left == Decimal("500.00")


@pytest.mark.asyncio
async def test_check_promo_code_usage_limit() -> None:
    with pytest.raises(CartPromoCodeLimitExceededError):
        await execute_check(
            promo_code=build_promo_code(usage_limit=1),
            usage_repository=FakePromoCodeUsageRepository(total_count=1),
        )


@pytest.mark.asyncio
async def test_check_promo_code_does_not_increment_usage() -> None:
    usage_repository = FakePromoCodeUsageRepository()

    await execute_check(usage_repository=usage_repository)

    assert usage_repository.created is False
