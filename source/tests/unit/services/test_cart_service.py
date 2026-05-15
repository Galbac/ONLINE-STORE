from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from source.config.settings import settings
from source.errors.auth import InactiveUserError
from source.errors.auth import (
    CartEmptyError,
    CartInsufficientStockError,
    CartItemAccessDeniedError,
    CartItemNotFoundError,
    CartPieceQuantityMustBeIntegerError,
    CartProductNotFoundError,
    CartQuantityStepError,
    CartPromoCodeExpiredError,
    CartPromoCodeInactiveError,
    CartPromoCodeLimitExceededError,
    CartPromoCodeMinAmountError,
    CartPromoCodeNotApplicableError,
    CartPromoCodeNotFoundError,
)
from source.schemas.pydantic.cart import ApplyPromoCodeRequest, CartItemUpdateRequest, CartResponse
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
from source.services.promo_code import PromoCodeService
from source.services.stock import StockService


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


class FakeCartRepository:
    def __init__(self) -> None:
        self.carts_by_user_id = {
            1: SimpleNamespace(id=10, user_id=1, promo_code_id=None),
            2: SimpleNamespace(id=20, user_id=2, promo_code_id=None),
        }
        self.requested_user_id: int | None = None

    async def get_or_create_by_user_id(self, *, session, user_id: int):
        self.requested_user_id = user_id
        cart = self.carts_by_user_id.get(user_id)
        if cart is None:
            cart = SimpleNamespace(id=100 + user_id, user_id=user_id, promo_code_id=None)
            self.carts_by_user_id[user_id] = cart
        return cart

    async def get_by_id(self, *, session, cart_id: int):
        return next((cart for cart in self.carts_by_user_id.values() if cart.id == cart_id), None)

    async def set_promo_code(self, *, session, cart, promo_code_id: int | None):
        cart.promo_code_id = promo_code_id
        return cart


class FakeCartItemRepository:
    def __init__(self, items_by_cart_id: dict[int, list[object]] | None = None) -> None:
        self.items_by_cart_id = items_by_cart_id if items_by_cart_id is not None else {10: []}
        self.requested_cart_id: int | None = None

    async def get_by_cart_id(self, *, session, cart_id: int):
        self.requested_cart_id = cart_id
        return self.items_by_cart_id.get(cart_id, [])

    async def get_by_id(self, *, session, cart_item_id: int):
        return next(
            (
                item
                for items in self.items_by_cart_id.values()
                for item in items
                if item.id == cart_item_id
            ),
            None,
        )

    async def get_by_cart_and_product_id(self, *, session, cart_id: int, product_id: int):
        return next(
            (item for item in self.items_by_cart_id.get(cart_id, []) if item.product_id == product_id),
            None,
        )

    async def create(self, *, session, cart_id: int, product, quantity: Decimal):
        item = build_cart_item(
            item_id=len(self.items_by_cart_id.get(cart_id, [])) + 1,
            cart_id=cart_id,
            product_id=product.id,
            name=product.name,
            quantity=quantity,
            unit=product.unit,
            price=product.price,
        )
        self.items_by_cart_id.setdefault(cart_id, []).append(item)
        return item

    async def update_quantity(self, *, session, cart_item, product, quantity: Decimal):
        cart_item.name = product.name
        cart_item.quantity = quantity
        cart_item.unit = product.unit
        cart_item.price = product.price
        cart_item.total_price = product.price * quantity
        return cart_item

    async def delete(self, *, session, cart_item) -> None:
        self.items_by_cart_id[cart_item.cart_id] = [
            item for item in self.items_by_cart_id.get(cart_item.cart_id, []) if item.id != cart_item.id
        ]

    async def delete_by_cart_id(self, *, session, cart_id: int) -> None:
        self.items_by_cart_id[cart_id] = []


class FakeProductRepository:
    def __init__(self, products: list[object] | None = None) -> None:
        self.products = products if products is not None else []
        self.requested_product_ids: list[int] | None = None

    async def get_by_ids(self, *, session, product_ids: list[int]):
        self.requested_product_ids = product_ids
        product_ids_set = set(product_ids)
        return [product for product in self.products if product.id in product_ids_set]

    async def get_by_id(self, *, session, product_id: int):
        return next((product for product in self.products if product.id == product_id), None)


class FakePromoCodeRepository:
    def __init__(self, promo_codes: list[object] | None = None) -> None:
        self.promo_codes = promo_codes if promo_codes is not None else []

    async def get_by_id(self, *, session, promo_code_id: int):
        return next((promo_code for promo_code in self.promo_codes if promo_code.id == promo_code_id), None)

    async def get_by_code(self, *, session, code: str):
        return next((promo_code for promo_code in self.promo_codes if promo_code.code == code), None)


class FakePromoCodeUsageRepository:
    def __init__(self, *, total_count: int = 0, user_count: int = 0) -> None:
        self.total_count = total_count
        self.user_count = user_count
        self.created_count = 0

    async def count_by_code(self, *, session, promo_code_id: int) -> int:
        return self.total_count

    async def count_by_user_and_code(self, *, session, user_id: int, promo_code_id: int) -> int:
        return self.user_count


def build_user(*, user_id: int = 1, is_active: bool = True, is_deleted: bool = False):
    return SimpleNamespace(id=user_id, is_active=is_active, is_deleted=is_deleted)


def build_cart_item(
    *,
    item_id: int = 1,
    cart_id: int = 10,
    product_id: int = 55,
    name: str = "Яблоки красные",
    quantity: Decimal = Decimal("1.5"),
    unit: str = "kg",
    price: Decimal = Decimal("999.00"),
):
    return SimpleNamespace(
        id=item_id,
        cart_id=cart_id,
        product_id=product_id,
        name=name,
        quantity=quantity,
        unit=unit,
        price=price,
        total_price=price * quantity,
    )


def build_product(
    *,
    product_id: int = 55,
    name: str = "Яблоки красные",
    slug: str = "yabloki-krasnye",
    unit: str = "kg",
    product_type: str = "weight",
    price: Decimal = Decimal("150.00"),
    old_price: Decimal | None = Decimal("180.00"),
    stock_quantity: Decimal = Decimal("30.5"),
    is_active: bool = True,
    is_deleted: bool = False,
    is_available: bool = True,
    quantity_step: Decimal = Decimal("0.5"),
    min_quantity: Decimal = Decimal("0.5"),
    category_id: int | None = 11,
):
    return SimpleNamespace(
        id=product_id,
        name=name,
        slug=slug,
        preview_image_url=f"/media/products/{slug}.png",
        unit=unit,
        product_type=product_type,
        price=price,
        old_price=old_price,
        stock_quantity=stock_quantity,
        is_active=is_active,
        is_deleted=is_deleted,
        is_available=is_available,
        quantity_step=quantity_step,
        min_quantity=min_quantity,
        category_id=category_id,
    )


def build_promo_code(
    *,
    promo_code_id: int = 1,
    code: str = "PROMO10",
    discount_type: str = "percent",
    discount_value: Decimal = Decimal("10"),
    min_order_amount: Decimal | None = None,
    usage_limit: int | None = None,
    per_user_usage_limit: int | None = None,
    applicable_category_id: int | None = None,
    applicable_product_id: int | None = None,
    allow_discounted_products: bool = True,
    is_active: bool = True,
    starts_at=None,
    ends_at=None,
):
    return SimpleNamespace(
        id=promo_code_id,
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        min_order_amount=min_order_amount,
        usage_limit=usage_limit,
        per_user_usage_limit=per_user_usage_limit,
        applicable_category_id=applicable_category_id,
        applicable_product_id=applicable_product_id,
        allow_discounted_products=allow_discounted_products,
        is_active=is_active,
        starts_at=starts_at,
        ends_at=ends_at,
    )


async def execute_get_current_cart(
    *,
    redis_service: FakeRedisService | None = None,
    cart_repository: FakeCartRepository | None = None,
    cart_item_repository: FakeCartItemRepository | None = None,
    product_repository: FakeProductRepository | None = None,
    user=None,
) -> CartResponse:
    return await CartService().get_current_cart(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        cart_cache_service=CartCacheService(),
        cart_repository=cart_repository or FakeCartRepository(),
        cart_item_repository=cart_item_repository or FakeCartItemRepository(),
        product_repository=product_repository or FakeProductRepository(),
        promo_code_repository=FakePromoCodeRepository(),
        cart_calculator_service=CartCalculatorService(),
        user=user or build_user(),
    )


async def execute_add_item(
    *,
    redis_service: FakeRedisService | None = None,
    cart_repository: FakeCartRepository | None = None,
    cart_item_repository: FakeCartItemRepository | None = None,
    product_repository: FakeProductRepository | None = None,
    user=None,
    product_id: int = 55,
    quantity: Decimal = Decimal("1.5"),
) -> CartResponse:
    return await CartService().add_item(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        cart_cache_service=CartCacheService(),
        cart_repository=cart_repository or FakeCartRepository(),
        cart_item_repository=cart_item_repository or FakeCartItemRepository(),
        product_repository=product_repository or FakeProductRepository([build_product()]),
        promo_code_repository=FakePromoCodeRepository(),
        cart_calculator_service=CartCalculatorService(),
        stock_service=StockService(),
        user=user or build_user(),
        product_id=product_id,
        quantity=quantity,
    )


async def execute_update_item(
    *,
    redis_service: FakeRedisService | None = None,
    cart_repository: FakeCartRepository | None = None,
    cart_item_repository: FakeCartItemRepository | None = None,
    product_repository: FakeProductRepository | None = None,
    user=None,
    cart_item_id: int = 1,
    quantity: Decimal = Decimal("2.5"),
) -> CartResponse:
    return await CartService().update_item_quantity(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        cart_cache_service=CartCacheService(),
        cart_repository=cart_repository or FakeCartRepository(),
        cart_item_repository=cart_item_repository or FakeCartItemRepository({10: [build_cart_item()]}),
        product_repository=product_repository or FakeProductRepository([build_product()]),
        promo_code_repository=FakePromoCodeRepository(),
        cart_calculator_service=CartCalculatorService(),
        stock_service=StockService(),
        user=user or build_user(),
        cart_item_id=cart_item_id,
        quantity=quantity,
    )


async def execute_delete_item(
    *,
    redis_service: FakeRedisService | None = None,
    cart_repository: FakeCartRepository | None = None,
    cart_item_repository: FakeCartItemRepository | None = None,
    product_repository: FakeProductRepository | None = None,
    user=None,
    cart_item_id: int = 1,
) -> CartResponse:
    return await CartService().delete_item(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        cart_cache_service=CartCacheService(),
        cart_repository=cart_repository or FakeCartRepository(),
        cart_item_repository=cart_item_repository or FakeCartItemRepository({10: [build_cart_item()]}),
        product_repository=product_repository or FakeProductRepository([build_product()]),
        promo_code_repository=FakePromoCodeRepository(),
        cart_calculator_service=CartCalculatorService(),
        user=user or build_user(),
        cart_item_id=cart_item_id,
    )


async def execute_clear_current_cart(
    *,
    redis_service: FakeRedisService | None = None,
    cart_repository: FakeCartRepository | None = None,
    cart_item_repository: FakeCartItemRepository | None = None,
    product_repository: FakeProductRepository | None = None,
    user=None,
) -> CartResponse:
    return await CartService().clear_current_cart(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        cart_cache_service=CartCacheService(),
        cart_repository=cart_repository or FakeCartRepository(),
        cart_item_repository=cart_item_repository or FakeCartItemRepository({10: [build_cart_item()]}),
        product_repository=product_repository or FakeProductRepository([build_product()]),
        promo_code_repository=FakePromoCodeRepository(),
        cart_calculator_service=CartCalculatorService(),
        user=user or build_user(),
    )


async def execute_apply_promo_code(
    *,
    redis_service: FakeRedisService | None = None,
    cart_repository: FakeCartRepository | None = None,
    cart_item_repository: FakeCartItemRepository | None = None,
    product_repository: FakeProductRepository | None = None,
    promo_code_repository: FakePromoCodeRepository | None = None,
    promo_code_usage_repository: FakePromoCodeUsageRepository | None = None,
    user=None,
    code: str = "PROMO10",
) -> CartResponse:
    return await CartService().apply_promo_code(
        session=object(),
        redis_service=redis_service or FakeRedisService(),
        cart_cache_service=CartCacheService(),
        cart_repository=cart_repository or FakeCartRepository(),
        cart_item_repository=cart_item_repository or FakeCartItemRepository({10: [build_cart_item(quantity=Decimal("1"))]}),
        product_repository=product_repository or FakeProductRepository([build_product(old_price=None)]),
        promo_code_repository=promo_code_repository or FakePromoCodeRepository([build_promo_code()]),
        promo_code_usage_repository=promo_code_usage_repository or FakePromoCodeUsageRepository(),
        cart_calculator_service=CartCalculatorService(),
        promo_code_service=PromoCodeService(),
        user=user or build_user(),
        code=code,
    )


@pytest.mark.asyncio
async def test_get_current_cart_from_postgresql_success() -> None:
    response = await execute_get_current_cart(
        cart_item_repository=FakeCartItemRepository({10: [build_cart_item()]}),
        product_repository=FakeProductRepository([build_product()]),
    )

    assert response.id == 10
    assert response.items_count == 1
    assert response.total_quantity == Decimal("1.5")
    assert response.subtotal == Decimal("270.000")
    assert response.discount_amount == Decimal("45.000")
    assert response.final_price == Decimal("225.000")
    assert response.items[0].price == Decimal("150.00")
    assert response.items[0].total_price == Decimal("270.000")
    assert response.items[0].final_price == Decimal("225.000")


@pytest.mark.asyncio
async def test_get_current_cart_from_redis_cache_success() -> None:
    redis_service = FakeRedisService()
    cached_response = CartResponse(
        id=10,
        items=[],
        items_count=0,
        total_quantity=Decimal("0"),
        subtotal=Decimal("0"),
        discount_amount=Decimal("0"),
        promo_discount_amount=Decimal("0"),
        final_price=Decimal("0"),
        warnings=[],
    )
    redis_service.values["cart:1"] = cached_response.model_dump_json()
    cart_repository = FakeCartRepository()

    response = await execute_get_current_cart(redis_service=redis_service, cart_repository=cart_repository)

    assert response.id == 10
    assert cart_repository.requested_user_id is None


@pytest.mark.asyncio
async def test_get_current_cart_empty_cart() -> None:
    response = await execute_get_current_cart()

    assert response.items == []
    assert response.items_count == 0
    assert response.total_quantity == Decimal("0")
    assert response.subtotal == Decimal("0")
    assert response.discount_amount == Decimal("0")
    assert response.promo_discount_amount == Decimal("0")
    assert response.delivery_price is None
    assert response.final_price == Decimal("0")
    assert response.warnings == []


@pytest.mark.asyncio
async def test_get_current_cart_piece_product() -> None:
    response = await execute_get_current_cart(
        cart_item_repository=FakeCartItemRepository({10: [build_cart_item(quantity=Decimal("2"), unit="pcs")]}),
        product_repository=FakeProductRepository(
            [
                build_product(
                    unit="pcs",
                    product_type="piece",
                    price=Decimal("50.00"),
                    old_price=None,
                    stock_quantity=Decimal("10"),
                ),
            ],
        ),
    )

    assert response.items[0].quantity == Decimal("2")
    assert response.items[0].unit == "pcs"
    assert response.items[0].product_type == "piece"
    assert response.final_price == Decimal("100.00")


@pytest.mark.asyncio
async def test_get_current_cart_weight_product() -> None:
    response = await execute_get_current_cart(
        cart_item_repository=FakeCartItemRepository({10: [build_cart_item(quantity=Decimal("1.5"), unit="kg")]}),
        product_repository=FakeProductRepository([build_product(product_type="weight", unit="kg")]),
    )

    assert response.items[0].quantity == Decimal("1.5")
    assert response.items[0].unit == "kg"
    assert response.items[0].product_type == "weight"


@pytest.mark.asyncio
async def test_get_current_cart_product_discount() -> None:
    response = await execute_get_current_cart(
        cart_item_repository=FakeCartItemRepository({10: [build_cart_item(quantity=Decimal("1"))]}),
        product_repository=FakeProductRepository(
            [build_product(price=Decimal("150.00"), old_price=Decimal("200.00"))],
        ),
    )

    assert response.subtotal == Decimal("200.00")
    assert response.discount_amount == Decimal("50.00")
    assert response.final_price == Decimal("150.00")


@pytest.mark.asyncio
async def test_get_current_cart_promo_code_defaults_to_null() -> None:
    response = await execute_get_current_cart()

    assert response.promo_code is None
    assert response.promo_discount_amount == Decimal("0")


@pytest.mark.asyncio
async def test_get_current_cart_unavailable_product_warning() -> None:
    response = await execute_get_current_cart(
        cart_item_repository=FakeCartItemRepository({10: [build_cart_item()]}),
        product_repository=FakeProductRepository([build_product(is_available=False)]),
    )

    assert response.items[0].is_available is False
    assert response.items[0].stock_warning == "Товар сейчас недоступен"
    assert response.warnings[0].message == "Товар сейчас недоступен"


@pytest.mark.asyncio
async def test_get_current_cart_insufficient_stock_warning() -> None:
    response = await execute_get_current_cart(
        cart_item_repository=FakeCartItemRepository({10: [build_cart_item(quantity=Decimal("5"))]}),
        product_repository=FakeProductRepository([build_product(stock_quantity=Decimal("2"))]),
    )

    assert response.items[0].stock_warning == "Недостаточно товара на складе"
    assert response.warnings[0].message == "Недостаточно товара на складе"


@pytest.mark.asyncio
async def test_get_current_cart_inactive_user_error() -> None:
    with pytest.raises(InactiveUserError):
        await execute_get_current_cart(user=build_user(is_active=False))


@pytest.mark.asyncio
async def test_get_current_cart_uses_only_current_user_cart() -> None:
    cart_repository = FakeCartRepository()
    cart_item_repository = FakeCartItemRepository(
        {
            10: [build_cart_item(product_id=55)],
            20: [build_cart_item(item_id=2, cart_id=20, product_id=77, name="Чужой товар")],
        },
    )

    response = await execute_get_current_cart(
        cart_repository=cart_repository,
        cart_item_repository=cart_item_repository,
        product_repository=FakeProductRepository([build_product(product_id=55)]),
        user=build_user(user_id=1),
    )

    assert cart_repository.requested_user_id == 1
    assert cart_item_repository.requested_cart_id == 10
    assert [item.product_id for item in response.items] == [55]


@pytest.mark.asyncio
async def test_get_current_cart_response_is_cached_in_redis() -> None:
    redis_service = FakeRedisService()

    await execute_get_current_cart(
        redis_service=redis_service,
        cart_item_repository=FakeCartItemRepository({10: [build_cart_item()]}),
        product_repository=FakeProductRepository([build_product()]),
    )

    assert "cart:1" in redis_service.values
    assert redis_service.ttls["cart:1"] == settings.cart.cache_ttl_seconds


@pytest.mark.asyncio
async def test_add_item_piece_product_success() -> None:
    response = await execute_add_item(
        product_repository=FakeProductRepository(
            [
                build_product(
                    product_type="piece",
                    unit="pcs",
                    quantity_step=Decimal("1"),
                    min_quantity=Decimal("1"),
                    stock_quantity=Decimal("10"),
                    old_price=None,
                ),
            ],
        ),
        quantity=Decimal("2"),
    )

    assert response.items[0].quantity == Decimal("2")
    assert response.items[0].product_type == "piece"


@pytest.mark.asyncio
async def test_add_item_weight_product_success() -> None:
    response = await execute_add_item(quantity=Decimal("1.5"))

    assert response.items[0].quantity == Decimal("1.5")
    assert response.items[0].product_type == "weight"


@pytest.mark.asyncio
async def test_add_item_existing_product_increases_quantity() -> None:
    cart_items = FakeCartItemRepository({10: [build_cart_item(quantity=Decimal("1"))]})

    response = await execute_add_item(cart_item_repository=cart_items, quantity=Decimal("1.5"))

    assert response.items[0].quantity == Decimal("2.5")


@pytest.mark.asyncio
async def test_add_item_product_not_found_error() -> None:
    with pytest.raises(CartProductNotFoundError):
        await execute_add_item(product_repository=FakeProductRepository([]))


@pytest.mark.asyncio
async def test_add_item_inactive_product_not_found_error() -> None:
    with pytest.raises(CartProductNotFoundError):
        await execute_add_item(product_repository=FakeProductRepository([build_product(is_active=False)]))


@pytest.mark.asyncio
async def test_add_item_deleted_product_not_found_error() -> None:
    with pytest.raises(CartProductNotFoundError):
        await execute_add_item(product_repository=FakeProductRepository([build_product(is_deleted=True)]))


@pytest.mark.asyncio
async def test_add_item_quantity_over_stock_error() -> None:
    with pytest.raises(CartInsufficientStockError):
        await execute_add_item(
            product_repository=FakeProductRepository([build_product(stock_quantity=Decimal("1"))]),
            quantity=Decimal("1.5"),
        )


@pytest.mark.asyncio
async def test_add_item_piece_fractional_quantity_error() -> None:
    with pytest.raises(CartPieceQuantityMustBeIntegerError):
        await execute_add_item(
            product_repository=FakeProductRepository(
                [build_product(product_type="piece", quantity_step=Decimal("1"), min_quantity=Decimal("1"))],
            ),
            quantity=Decimal("1.5"),
        )


@pytest.mark.asyncio
async def test_add_item_weight_invalid_step_error() -> None:
    with pytest.raises(CartQuantityStepError):
        await execute_add_item(quantity=Decimal("1.3"))


@pytest.mark.asyncio
async def test_add_item_invalidates_cart_cache() -> None:
    redis_service = FakeRedisService()

    await execute_add_item(redis_service=redis_service)

    assert redis_service.deleted == ["cart:1", "cart:summary:1"]


@pytest.mark.asyncio
async def test_update_item_piece_quantity_success() -> None:
    response = await execute_update_item(
        cart_item_repository=FakeCartItemRepository({10: [build_cart_item(quantity=Decimal("1"), unit="pcs")]}),
        product_repository=FakeProductRepository(
            [build_product(product_type="piece", unit="pcs", quantity_step=Decimal("1"), min_quantity=Decimal("1"), old_price=None)],
        ),
        quantity=Decimal("2"),
    )

    assert response.items[0].quantity == Decimal("2")
    assert response.items[0].product_type == "piece"


@pytest.mark.asyncio
async def test_update_item_weight_quantity_success() -> None:
    response = await execute_update_item(quantity=Decimal("2.5"))

    assert response.items[0].quantity == Decimal("2.5")
    assert response.items[0].product_type == "weight"


@pytest.mark.asyncio
async def test_update_item_foreign_cart_error() -> None:
    with pytest.raises(CartItemAccessDeniedError):
        await execute_update_item(
            cart_item_repository=FakeCartItemRepository(
                {20: [build_cart_item(item_id=2, cart_id=20, product_id=55)]},
            ),
            cart_item_id=2,
            user=build_user(user_id=1),
        )


@pytest.mark.asyncio
async def test_update_item_not_found_error() -> None:
    with pytest.raises(CartItemNotFoundError):
        await execute_update_item(cart_item_id=999)


def test_update_item_quantity_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        CartItemUpdateRequest(quantity=Decimal("0"))


@pytest.mark.asyncio
async def test_update_item_piece_fractional_quantity_error() -> None:
    with pytest.raises(CartPieceQuantityMustBeIntegerError):
        await execute_update_item(
            product_repository=FakeProductRepository(
                [build_product(product_type="piece", quantity_step=Decimal("1"), min_quantity=Decimal("1"))],
            ),
            quantity=Decimal("1.5"),
        )


@pytest.mark.asyncio
async def test_update_item_weight_invalid_step_error() -> None:
    with pytest.raises(CartQuantityStepError):
        await execute_update_item(quantity=Decimal("1.3"))


@pytest.mark.asyncio
async def test_update_item_insufficient_stock_error() -> None:
    with pytest.raises(CartInsufficientStockError):
        await execute_update_item(
            product_repository=FakeProductRepository([build_product(stock_quantity=Decimal("2"))]),
            quantity=Decimal("2.5"),
        )


@pytest.mark.asyncio
async def test_update_item_invalidates_cart_cache() -> None:
    redis_service = FakeRedisService()

    await execute_update_item(redis_service=redis_service)

    assert redis_service.deleted == ["cart:1", "cart:summary:1"]


@pytest.mark.asyncio
async def test_delete_item_success() -> None:
    response = await execute_delete_item()

    assert response.items == []
    assert response.items_count == 0
    assert response.final_price == Decimal("0")


@pytest.mark.asyncio
async def test_delete_item_foreign_cart_error() -> None:
    with pytest.raises(CartItemAccessDeniedError):
        await execute_delete_item(
            cart_item_repository=FakeCartItemRepository(
                {20: [build_cart_item(item_id=2, cart_id=20, product_id=55)]},
            ),
            cart_item_id=2,
            user=build_user(user_id=1),
        )


@pytest.mark.asyncio
async def test_delete_item_not_found_error() -> None:
    with pytest.raises(CartItemNotFoundError):
        await execute_delete_item(cart_item_id=999)


@pytest.mark.asyncio
async def test_delete_item_recalculates_remaining_cart() -> None:
    response = await execute_delete_item(
        cart_item_repository=FakeCartItemRepository(
            {
                10: [
                    build_cart_item(item_id=1, product_id=55, quantity=Decimal("1")),
                    build_cart_item(item_id=2, product_id=56, name="Бананы", quantity=Decimal("2")),
                ],
            },
        ),
        product_repository=FakeProductRepository(
            [
                build_product(product_id=55),
                build_product(product_id=56, name="Бананы", slug="banany", price=Decimal("50"), old_price=None),
            ],
        ),
    )

    assert [item.product_id for item in response.items] == [56]
    assert response.final_price == Decimal("100")


@pytest.mark.asyncio
async def test_delete_item_empty_cart_has_no_promo_code() -> None:
    response = await execute_delete_item()

    assert response.promo_code is None
    assert response.promo_discount_amount == Decimal("0")


@pytest.mark.asyncio
async def test_delete_item_invalidates_cart_cache() -> None:
    redis_service = FakeRedisService()

    await execute_delete_item(redis_service=redis_service)

    assert redis_service.deleted == ["cart:1", "cart:summary:1"]


@pytest.mark.asyncio
async def test_clear_current_cart_success() -> None:
    response = await execute_clear_current_cart()

    assert response.items == []
    assert response.items_count == 0
    assert response.final_price == Decimal("0")


@pytest.mark.asyncio
async def test_clear_current_cart_empty_cart_success() -> None:
    response = await execute_clear_current_cart(
        cart_item_repository=FakeCartItemRepository({10: []}),
        product_repository=FakeProductRepository([]),
    )

    assert response.items == []
    assert response.items_count == 0
    assert response.final_price == Decimal("0")


@pytest.mark.asyncio
async def test_clear_current_cart_has_no_promo_code() -> None:
    response = await execute_clear_current_cart()

    assert response.promo_code is None
    assert response.promo_discount_amount == Decimal("0")


@pytest.mark.asyncio
async def test_clear_current_cart_uses_only_current_user_cart() -> None:
    cart_item_repository = FakeCartItemRepository(
        {
            10: [build_cart_item()],
            20: [build_cart_item(item_id=2, cart_id=20, product_id=77, name="Чужой товар")],
        },
    )

    await execute_clear_current_cart(
        cart_item_repository=cart_item_repository,
        product_repository=FakeProductRepository([build_product()]),
        user=build_user(user_id=1),
    )

    assert cart_item_repository.items_by_cart_id[10] == []
    assert len(cart_item_repository.items_by_cart_id[20]) == 1


@pytest.mark.asyncio
async def test_clear_current_cart_invalidates_cart_cache() -> None:
    redis_service = FakeRedisService()

    await execute_clear_current_cart(redis_service=redis_service)

    assert redis_service.deleted == ["cart:1", "cart:summary:1"]


@pytest.mark.asyncio
async def test_clear_current_cart_inactive_user_error() -> None:
    with pytest.raises(InactiveUserError):
        await execute_clear_current_cart(user=build_user(is_active=False))


def test_apply_promo_code_request_normalizes_code() -> None:
    assert ApplyPromoCodeRequest(code=" promo10 ").code == "PROMO10"


@pytest.mark.asyncio
async def test_apply_promo_code_percent_success() -> None:
    response = await execute_apply_promo_code()

    assert response.promo_code is not None
    assert response.promo_code.code == "PROMO10"
    assert response.promo_discount_amount == Decimal("15.00")
    assert response.final_price == Decimal("135.00")


@pytest.mark.asyncio
async def test_apply_promo_code_fixed_success() -> None:
    response = await execute_apply_promo_code(
        promo_code_repository=FakePromoCodeRepository(
            [build_promo_code(discount_type="fixed", discount_value=Decimal("25"))],
        ),
    )

    assert response.promo_discount_amount == Decimal("25")
    assert response.final_price == Decimal("125.00")


@pytest.mark.asyncio
async def test_apply_promo_code_empty_cart_error() -> None:
    with pytest.raises(CartEmptyError):
        await execute_apply_promo_code(
            cart_item_repository=FakeCartItemRepository({10: []}),
            product_repository=FakeProductRepository([]),
        )


@pytest.mark.asyncio
async def test_apply_promo_code_not_found_error() -> None:
    with pytest.raises(CartPromoCodeNotFoundError):
        await execute_apply_promo_code(promo_code_repository=FakePromoCodeRepository([]))


@pytest.mark.asyncio
async def test_apply_promo_code_inactive_error() -> None:
    with pytest.raises(CartPromoCodeInactiveError):
        await execute_apply_promo_code(
            promo_code_repository=FakePromoCodeRepository([build_promo_code(is_active=False)]),
        )


@pytest.mark.asyncio
async def test_apply_promo_code_expired_error() -> None:
    with pytest.raises(CartPromoCodeExpiredError):
        await execute_apply_promo_code(
            promo_code_repository=FakePromoCodeRepository(
                [build_promo_code(ends_at=datetime.now(UTC) - timedelta(days=1))],
            ),
        )


@pytest.mark.asyncio
async def test_apply_promo_code_min_amount_error() -> None:
    with pytest.raises(CartPromoCodeMinAmountError):
        await execute_apply_promo_code(
            promo_code_repository=FakePromoCodeRepository(
                [build_promo_code(min_order_amount=Decimal("200"))],
            ),
        )


@pytest.mark.asyncio
async def test_apply_promo_code_usage_limit_error() -> None:
    with pytest.raises(CartPromoCodeLimitExceededError):
        await execute_apply_promo_code(
            promo_code_repository=FakePromoCodeRepository([build_promo_code(usage_limit=1)]),
            promo_code_usage_repository=FakePromoCodeUsageRepository(total_count=1),
        )


@pytest.mark.asyncio
async def test_apply_promo_code_not_applicable_error() -> None:
    with pytest.raises(CartPromoCodeNotApplicableError):
        await execute_apply_promo_code(
            promo_code_repository=FakePromoCodeRepository(
                [build_promo_code(applicable_product_id=999)],
            ),
        )


@pytest.mark.asyncio
async def test_apply_promo_code_invalidates_cart_cache() -> None:
    redis_service = FakeRedisService()

    await execute_apply_promo_code(redis_service=redis_service)

    assert redis_service.deleted == ["cart:1", "cart:summary:1"]


@pytest.mark.asyncio
async def test_apply_promo_code_does_not_increase_usage_count() -> None:
    usage_repository = FakePromoCodeUsageRepository()

    await execute_apply_promo_code(promo_code_usage_repository=usage_repository)

    assert usage_repository.created_count == 0
