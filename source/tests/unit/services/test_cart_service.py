from decimal import Decimal
from types import SimpleNamespace

import pytest

from source.config.settings import settings
from source.errors.auth import InactiveUserError
from source.errors.auth import (
    CartInsufficientStockError,
    CartPieceQuantityMustBeIntegerError,
    CartProductNotFoundError,
    CartQuantityStepError,
)
from source.schemas.pydantic.cart import CartResponse
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
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
            1: SimpleNamespace(id=10, user_id=1),
            2: SimpleNamespace(id=20, user_id=2),
        }
        self.requested_user_id: int | None = None

    async def get_or_create_by_user_id(self, *, session, user_id: int):
        self.requested_user_id = user_id
        cart = self.carts_by_user_id.get(user_id)
        if cart is None:
            cart = SimpleNamespace(id=100 + user_id, user_id=user_id)
            self.carts_by_user_id[user_id] = cart
        return cart


class FakeCartItemRepository:
    def __init__(self, items_by_cart_id: dict[int, list[object]] | None = None) -> None:
        self.items_by_cart_id = items_by_cart_id if items_by_cart_id is not None else {10: []}
        self.requested_cart_id: int | None = None

    async def get_by_cart_id(self, *, session, cart_id: int):
        self.requested_cart_id = cart_id
        return self.items_by_cart_id.get(cart_id, [])

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
        cart_calculator_service=CartCalculatorService(),
        stock_service=StockService(),
        user=user or build_user(),
        product_id=product_id,
        quantity=quantity,
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
