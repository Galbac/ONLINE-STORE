import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime, UTC
from fastapi import HTTPException, status

from source.db.models.choises.enum import UserRole
from source.db.models.order import Order
from source.db.models.product import Product
from source.db.models.store_settings import StoreSettings
from source.db.models.user import User
from source.schemas.pydantic.order import OrderCreateRequest
from source.schemas.pydantic.promo_code import PromoCodeApplyRequest, PromoCodeCheckRequest
from source.schemas.pydantic.stock_alert import StockAlertSubscribeRequest
from source.api.api_v1.views.loyalty import get_my_referral
from source.api.api_v1.views.orders import get_order_receipt, get_order_tracking
from source.api.api_v1.views.products import (
    get_popular_searches,
    get_product_recommendations,
    get_search_suggestions,
    subscribe_to_stock_alert,
)
from source.api.api_v1.views.promo_codes import apply_promo_code, check_promo_code


def unwrap(fn):
    return getattr(fn, "__dishka_orig_func__", fn)


@pytest.mark.asyncio
async def test_promo_codes_admin_kill_switch():
    session = AsyncMock()
    settings_repo = AsyncMock()

    # When promo codes are disabled by admin
    store_settings = StoreSettings(promo_codes_enabled=False)
    settings_repo.get_or_create_default.return_value = (store_settings, False)

    with pytest.raises(HTTPException) as exc_info:
        await unwrap(check_promo_code)(
            body=PromoCodeCheckRequest(code="SALE20"),
            session=session,
            settings_repository=settings_repo,
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Промокоды временно отключены" in exc_info.value.detail

    user = User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True)
    with pytest.raises(HTTPException) as exc_info2:
        await unwrap(apply_promo_code)(
            body=PromoCodeApplyRequest(code="SALE20"),
            current_user=user,
            session=session,
            settings_repository=settings_repo,
        )
    assert exc_info2.value.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_referral_program_admin_kill_switch():
    session = AsyncMock()
    settings_repo = AsyncMock()
    user = User(id=42, name="Елена", role=UserRole.CUSTOMER, is_active=True)

    # When referral is disabled
    store_settings = StoreSettings(referral_program_enabled=False)
    settings_repo.get_or_create_default.return_value = (store_settings, False)

    with pytest.raises(HTTPException) as exc_info:
        await unwrap(get_my_referral)(
            current_user=user,
            session=session,
            settings_repository=settings_repo,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    # When referral is enabled
    store_settings.referral_program_enabled = True
    ref_response = await unwrap(get_my_referral)(
        current_user=user,
        session=session,
        settings_repository=settings_repo,
    )
    assert ref_response.code.startswith("REF-")
    assert ref_response.reward_amount == 500


@pytest.mark.asyncio
async def test_search_popular_and_suggestions():
    session = AsyncMock()
    cat_repo = AsyncMock()
    prod_repo = AsyncMock()

    # Test popular searches
    popular = await unwrap(get_popular_searches)()
    assert len(popular) > 0
    assert "Фрукты и ягоды" in popular

    # Short query (< 2 chars) returns empty lists without DB calls
    short_res = await unwrap(get_search_suggestions)(
        q="a",
        session=session,
        product_repository=prod_repo,
        category_repository=cat_repo,
    )
    assert short_res.categories == []
    assert short_res.products == []

    # Valid query
    cat_repo.search_by_name.return_value = []
    prod_repo.search_active.return_value = []
    res = await unwrap(get_search_suggestions)(
        q="яблоки",
        session=session,
        product_repository=prod_repo,
        category_repository=cat_repo,
    )
    assert res.query == "яблоки"
    assert cat_repo.search_by_name.called


@pytest.mark.asyncio
async def test_stock_alert_subscription():
    session = AsyncMock()
    prod_repo = AsyncMock()
    alert_repo = AsyncMock()
    commiter = AsyncMock()

    # Product not found
    prod_repo.get_by_id.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await unwrap(subscribe_to_stock_alert)(
            product_id=999,
            body=StockAlertSubscribeRequest(email="test@example.com"),
            session=session,
            product_repository=prod_repo,
            stock_alert_repository=alert_repo,
            commiter=commiter,
        )
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    # Valid subscription
    product = Product(id=10, name="Товар", is_active=True)
    prod_repo.get_by_id.return_value = product
    response = await unwrap(subscribe_to_stock_alert)(
        product_id=10,
        body=StockAlertSubscribeRequest(email="test@example.com"),
        session=session,
        product_repository=prod_repo,
        stock_alert_repository=alert_repo,
        commiter=commiter,
    )
    assert response.is_subscribed is True
    assert alert_repo.create_alert.called
    assert commiter.commit.called


@pytest.mark.asyncio
async def test_product_recommendations():
    session = AsyncMock()
    prod_repo = AsyncMock()

    prod_repo.get_by_id.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await unwrap(get_product_recommendations)(
            product_id=999,
            session=session,
            product_repository=prod_repo,
        )
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    product = Product(id=5, name="Чай", category_id=2, is_active=True)
    prod_repo.get_by_id.return_value = product
    prod_repo.get_similar_active.return_value = []
    rec = await unwrap(get_product_recommendations)(
        product_id=5,
        session=session,
        product_repository=prod_repo,
    )
    assert rec.product_id == 5
    assert prod_repo.get_similar_active.called


@pytest.mark.asyncio
async def test_order_receipt_permissions():
    session = AsyncMock()
    order_repo = AsyncMock()

    owner = User(id=1, name="Иван", role=UserRole.CUSTOMER, is_active=True)
    other_user = User(id=2, name="Петр", role=UserRole.CUSTOMER, is_active=True)

    order = Order(
        id=123,
        order_number="ORD-123",
        user_id=1,
        final_price=Decimal("1250.00"),
        status="delivered",
        delivery_type="delivery",
        customer_name="Иван",
        customer_phone="+79990000000",
        updated_date=datetime.now(UTC),
    )
    order_repo.get_by_id.return_value = order

    # Non-owner customer gets 403
    with pytest.raises(HTTPException) as exc_info:
        await unwrap(get_order_receipt)(
            order_id=123,
            current_user=other_user,
            session=session,
            order_repository=order_repo,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    # Owner gets receipt
    receipt = await unwrap(get_order_receipt)(
        order_id=123,
        current_user=owner,
        session=session,
        order_repository=order_repo,
    )
    assert receipt.order_number == "ORD-123"
    assert "receipt.ofd.ru" in receipt.receipt_url
    assert receipt.total_amount == Decimal("1250.00")
