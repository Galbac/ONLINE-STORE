from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from source.api.api_v1.views.cart import (
    add_cart_item,
    apply_promo_code,
    clear_cart,
    delete_cart_item,
    get_cart,
    get_cart_summary,
    remove_promo_code,
    update_cart_item,
)
from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import (
    CartInsufficientStockError,
    CartItemAccessDeniedError,
    CartItemNotFoundError,
    CartProductNotFoundError,
    CartProductUnavailableError,
    CartPromoCodeExpiredError,
    InactiveUserError,
)
from source.schemas.pydantic.cart import (
    ApplyPromoCodeRequest,
    CartItemCreateRequest,
    CartItemUpdateRequest,
    CartResponse,
    CartSummaryResponse,
    MessageCartResponse,
)


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.fixture
def active_user():
    return User(id=1, name="Клиент", role=UserRole.CUSTOMER, is_active=True, is_deleted=False)


@pytest.fixture
def fake_cart_response():
    return CartResponse(
        id=1,
        items=[],
        promo_code=None,
        items_count=0,
        total_quantity=Decimal("0"),
        subtotal=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        promo_discount_amount=Decimal("0.00"),
        delivery_price=None,
        final_price=Decimal("0.00"),
        warnings=[],
    )


# ---------------------------------------------------------
# GET /cart
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_cart_success(active_user, fake_cart_response):
    cart_service = AsyncMock()
    cart_service.get_current_cart.return_value = fake_cart_response

    response = await unwrap(get_cart)(
        current_user=active_user,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=AsyncMock(),
        cart_calculator_service=MagicMock(),
        cart_repository=AsyncMock(),
        cart_item_repository=AsyncMock(),
        product_repository=AsyncMock(),
        promo_code_repository=AsyncMock(),
    )
    assert response.id == 1
    assert response.items_count == 0


@pytest.mark.asyncio
async def test_get_cart_inactive_user_forbidden():
    inactive_user = User(id=2, name="Блок", role=UserRole.CUSTOMER, is_active=False)
    cart_service = AsyncMock()
    cart_service.get_current_cart.side_effect = InactiveUserError

    with pytest.raises(HTTPException) as exc:
        await unwrap(get_cart)(
            current_user=inactive_user,
            session=AsyncMock(),
            redis_service=AsyncMock(),
            cart_service=cart_service,
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            product_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
        )
    assert exc.value.status_code == 403


# ---------------------------------------------------------
# GET /cart/summary
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_cart_summary_success(active_user):
    cart_service = AsyncMock()
    summary = CartSummaryResponse(
        items_count=2,
        total_quantity=Decimal("3"),
        subtotal=Decimal("250.00"),
        discount_amount=Decimal("0.00"),
        promo_discount_amount=Decimal("0.00"),
        delivery_price=None,
        final_price=Decimal("250.00"),
        has_warnings=False,
        warnings_count=0,
    )
    cart_service.get_cart_summary.return_value = summary

    response = await unwrap(get_cart_summary)(
        current_user=active_user,
        session=AsyncMock(),
        redis_service=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=AsyncMock(),
        cart_calculator_service=MagicMock(),
        cart_repository=AsyncMock(),
        cart_item_repository=AsyncMock(),
        product_repository=AsyncMock(),
    )
    assert response.items_count == 2
    assert response.final_price == Decimal("250.00")


# ---------------------------------------------------------
# POST /cart/items
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_create_cart_item_success(active_user, fake_cart_response):
    cart_service = AsyncMock()
    cart_service.add_item.return_value = fake_cart_response
    commiter = AsyncMock()

    body = CartItemCreateRequest(product_id=10, quantity=Decimal("2"))
    response = await unwrap(add_cart_item)(
        body=body,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=AsyncMock(),
        cart_calculator_service=MagicMock(),
        cart_repository=AsyncMock(),
        cart_item_repository=AsyncMock(),
        product_repository=AsyncMock(),
        promo_code_repository=AsyncMock(),
        stock_service=MagicMock(),
    )
    assert response.message == "Товар добавлен в корзину"
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_create_cart_item_insufficient_stock(active_user):
    cart_service = AsyncMock()
    cart_service.add_item.side_effect = CartInsufficientStockError
    commiter = AsyncMock()

    body = CartItemCreateRequest(product_id=10, quantity=Decimal("100"))
    with pytest.raises(HTTPException) as exc:
        await unwrap(add_cart_item)(
            body=body,
            current_user=active_user,
            session=AsyncMock(),
            commiter=commiter,
            redis_service=AsyncMock(),
            cart_service=cart_service,
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            product_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
            stock_service=MagicMock(),
        )
    assert exc.value.status_code == 409
    assert commiter.rollback.called


@pytest.mark.asyncio
async def test_create_cart_item_not_found(active_user):
    cart_service = AsyncMock()
    cart_service.add_item.side_effect = CartProductNotFoundError
    commiter = AsyncMock()

    body = CartItemCreateRequest(product_id=999, quantity=Decimal("1"))
    with pytest.raises(HTTPException) as exc:
        await unwrap(add_cart_item)(
            body=body,
            current_user=active_user,
            session=AsyncMock(),
            commiter=commiter,
            redis_service=AsyncMock(),
            cart_service=cart_service,
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            product_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
            stock_service=MagicMock(),
        )
    assert exc.value.status_code == 404
    assert commiter.rollback.called


# ---------------------------------------------------------
# PATCH /cart/items/{cart_item_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_update_cart_item_success(active_user, fake_cart_response):
    cart_service = AsyncMock()
    cart_service.update_item_quantity.return_value = fake_cart_response
    commiter = AsyncMock()

    body = CartItemUpdateRequest(quantity=Decimal("3"))
    response = await unwrap(update_cart_item)(
        cart_item_id=15,
        body=body,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=AsyncMock(),
        cart_calculator_service=MagicMock(),
        cart_repository=AsyncMock(),
        cart_item_repository=AsyncMock(),
        product_repository=AsyncMock(),
        promo_code_repository=AsyncMock(),
        stock_service=MagicMock(),
    )
    assert response.message == "Количество товара обновлено"
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_update_cart_item_not_found(active_user):
    cart_service = AsyncMock()
    cart_service.update_item_quantity.side_effect = CartItemNotFoundError
    commiter = AsyncMock()

    body = CartItemUpdateRequest(quantity=Decimal("3"))
    with pytest.raises(HTTPException) as exc:
        await unwrap(update_cart_item)(
            cart_item_id=999,
            body=body,
            current_user=active_user,
            session=AsyncMock(),
            commiter=commiter,
            redis_service=AsyncMock(),
            cart_service=cart_service,
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            product_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
            stock_service=MagicMock(),
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------
# DELETE /cart/items/{cart_item_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_cart_item_success(active_user, fake_cart_response):
    cart_service = AsyncMock()
    cart_service.delete_item.return_value = fake_cart_response
    commiter = AsyncMock()

    response = await unwrap(delete_cart_item)(
        cart_item_id=15,
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=AsyncMock(),
        cart_calculator_service=MagicMock(),
        cart_repository=AsyncMock(),
        cart_item_repository=AsyncMock(),
        product_repository=AsyncMock(),
        promo_code_repository=AsyncMock(),
    )
    assert response.message == "Товар удалён из корзины"
    assert commiter.commit.called


# ---------------------------------------------------------
# DELETE /cart
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_clear_cart_success(active_user, fake_cart_response):
    cart_service = AsyncMock()
    cart_service.clear_current_cart.return_value = fake_cart_response
    commiter = AsyncMock()

    response = await unwrap(clear_cart)(
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=AsyncMock(),
        cart_calculator_service=MagicMock(),
        cart_repository=AsyncMock(),
        cart_item_repository=AsyncMock(),
        product_repository=AsyncMock(),
        promo_code_repository=AsyncMock(),
    )
    assert response.message == "Корзина очищена"
    assert commiter.commit.called


# ---------------------------------------------------------
# DELETE /cart/promo-code
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_promo_code_success(active_user, fake_cart_response):
    cart_service = AsyncMock()
    cart_service.remove_promo_code.return_value = fake_cart_response
    commiter = AsyncMock()

    response = await unwrap(remove_promo_code)(
        current_user=active_user,
        session=AsyncMock(),
        commiter=commiter,
        redis_service=AsyncMock(),
        cart_service=cart_service,
        cart_cache_service=AsyncMock(),
        cart_calculator_service=MagicMock(),
        cart_repository=AsyncMock(),
        cart_item_repository=AsyncMock(),
        product_repository=AsyncMock(),
        promo_code_repository=AsyncMock(),
    )
    assert response.message == "Промокод удалён"
    assert commiter.commit.called


# ---------------------------------------------------------
# POST /cart/apply-promo-code
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_promo_code_expired_error(active_user):
    cart_service = AsyncMock()
    cart_service.apply_promo_code.side_effect = CartPromoCodeExpiredError
    commiter = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await unwrap(apply_promo_code)(
            body=ApplyPromoCodeRequest(code="EXPIRED"),
            current_user=active_user,
            session=AsyncMock(),
            commiter=commiter,
            redis_service=AsyncMock(),
            cart_service=cart_service,
            promo_code_service=AsyncMock(),
            cart_cache_service=AsyncMock(),
            cart_calculator_service=MagicMock(),
            cart_repository=AsyncMock(),
            cart_item_repository=AsyncMock(),
            product_repository=AsyncMock(),
            promo_code_repository=AsyncMock(),
            promo_code_usage_repository=AsyncMock(),
        )
    assert exc.value.status_code == 409
    assert "истёк" in exc.value.detail.lower()
