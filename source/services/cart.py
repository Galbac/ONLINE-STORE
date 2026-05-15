from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.cart import Cart
from source.db.models.product import Product
from source.config.settings import settings
from source.errors.auth import (
    CartEmptyError,
    CartItemAccessDeniedError,
    CartItemNotFoundError,
    CartPromoCodeNotFoundError,
    CartProductNotFoundError,
    CartProductUnavailableError,
    InactiveUserError,
)
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.product import ProductRepository
from source.repositories.promo_code import PromoCodeRepository, PromoCodeUsageRepository
from source.schemas.pydantic.cart import (
    CartItemResponse as DetailedCartItemResponse,
    CartResponse as DetailedCartResponse,
    CartWarningResponse,
)
from source.schemas.pydantic.profile import CartItemResponse, CartResponse
from source.services.cart_cache import CartCacheService
from source.services.redis import RedisService
from source.services.stock import StockService
from source.services.promo_code import PromoCodeService
from source.utils.cart import calculate_cart_totals


class CartCalculatorService:
    def calculate(
        self,
        *,
        cart_id: int,
        cart_items: list,
        products_by_id: dict[int, Product],
        promo_code=None,
        promo_discount_amount: Decimal = Decimal("0"),
    ) -> DetailedCartResponse:
        items: list[DetailedCartItemResponse] = []
        warnings: list[CartWarningResponse] = []
        subtotal = Decimal("0")
        discount_amount = Decimal("0")
        total_quantity = Decimal("0")

        for cart_item in cart_items:
            product = products_by_id.get(cart_item.product_id)
            stock_warning = None

            if product is None:
                stock_warning = "Товар больше недоступен"
                warnings.append(CartWarningResponse(product_id=cart_item.product_id, message=stock_warning))
                price = cart_item.price
                old_price = None
                item_total = price * cart_item.quantity
                item_discount = Decimal("0")
                item_final = item_total
                item = DetailedCartItemResponse(
                    id=cart_item.id,
                    product_id=cart_item.product_id,
                    name=cart_item.name,
                    quantity=cart_item.quantity,
                    unit=cart_item.unit,
                    price=price,
                    old_price=old_price,
                    discount_amount=item_discount,
                    total_price=item_total,
                    final_price=item_final,
                    is_available=False,
                    stock_quantity=Decimal("0"),
                    stock_warning=stock_warning,
                )
            else:
                is_available = product.is_active and not product.is_deleted and product.is_available and product.stock_quantity > 0
                if not is_available:
                    stock_warning = "Товар сейчас недоступен"
                    warnings.append(CartWarningResponse(product_id=product.id, message=stock_warning))
                elif product.stock_quantity < cart_item.quantity:
                    stock_warning = "Недостаточно товара на складе"
                    warnings.append(CartWarningResponse(product_id=product.id, message=stock_warning))

                old_price = product.old_price if product.old_price is not None and product.old_price > product.price else None
                base_price = old_price or product.price
                item_total = base_price * cart_item.quantity
                item_final = product.price * cart_item.quantity
                item_discount = item_total - item_final
                item = DetailedCartItemResponse(
                    id=cart_item.id,
                    product_id=product.id,
                    name=product.name,
                    slug=product.slug,
                    preview_image_url=product.preview_image_url,
                    quantity=cart_item.quantity,
                    unit=product.unit,
                    product_type=product.product_type,
                    price=product.price,
                    old_price=old_price,
                    discount_amount=item_discount,
                    total_price=item_total,
                    final_price=item_final,
                    is_available=is_available,
                    stock_quantity=product.stock_quantity,
                    stock_warning=stock_warning,
                )

            items.append(item)
            subtotal += item.total_price
            discount_amount += item.discount_amount
            total_quantity += item.quantity

        final_price = subtotal - discount_amount - promo_discount_amount
        if final_price < 0:
            final_price = Decimal("0")

        return DetailedCartResponse(
            id=cart_id,
            items=items,
            promo_code=(
                None
                if promo_code is None
                else {"code": promo_code.code, "discount_amount": promo_discount_amount}
            ),
            items_count=len(items),
            total_quantity=total_quantity,
            subtotal=subtotal,
            discount_amount=discount_amount,
            promo_discount_amount=promo_discount_amount,
            delivery_price=None,
            final_price=final_price,
            warnings=warnings,
        )


class CartService:
    async def clear_current_cart(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        cart_cache_service: CartCacheService,
        cart_repository: CartRepository,
        cart_item_repository: CartItemRepository,
        product_repository: ProductRepository,
        promo_code_repository: PromoCodeRepository,
        cart_calculator_service: CartCalculatorService,
        user,
    ) -> DetailedCartResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cart = await self.get_or_create_cart(
            session=session,
            cart_repository=cart_repository,
            user_id=user.id,
        )
        await self.clear_cart(
            session=session,
            cart_item_repository=cart_item_repository,
            cart=cart,
        )
        await cart_repository.set_promo_code(session=session, cart=cart, promo_code_id=None)
        response = await self.recalculate_current_cart(
            session=session,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            cart=cart,
        )
        await cart_cache_service.invalidate_cart(redis_service=redis_service, user_id=user.id)
        return response

    async def delete_item(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        cart_cache_service: CartCacheService,
        cart_repository: CartRepository,
        cart_item_repository: CartItemRepository,
        product_repository: ProductRepository,
        promo_code_repository: PromoCodeRepository,
        cart_calculator_service: CartCalculatorService,
        user,
        cart_item_id: int,
    ) -> DetailedCartResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cart_item = await cart_item_repository.get_by_id(session=session, cart_item_id=cart_item_id)
        if cart_item is None:
            raise CartItemNotFoundError

        cart = await cart_repository.get_by_id(session=session, cart_id=cart_item.cart_id)
        if cart is None:
            raise CartItemNotFoundError
        if cart.user_id != user.id:
            raise CartItemAccessDeniedError

        await cart_item_repository.delete(session=session, cart_item=cart_item)
        if not await cart_item_repository.get_by_cart_id(session=session, cart_id=cart.id):
            await cart_repository.set_promo_code(session=session, cart=cart, promo_code_id=None)
        response = await self.recalculate_current_cart(
            session=session,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            cart=cart,
        )
        await cart_cache_service.invalidate_cart(redis_service=redis_service, user_id=user.id)
        return response

    async def update_item_quantity(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        cart_cache_service: CartCacheService,
        cart_repository: CartRepository,
        cart_item_repository: CartItemRepository,
        product_repository: ProductRepository,
        promo_code_repository: PromoCodeRepository,
        cart_calculator_service: CartCalculatorService,
        stock_service: StockService,
        user,
        cart_item_id: int,
        quantity: Decimal,
    ) -> DetailedCartResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cart_item = await cart_item_repository.get_by_id(session=session, cart_item_id=cart_item_id)
        if cart_item is None:
            raise CartItemNotFoundError

        cart = await cart_repository.get_by_id(session=session, cart_id=cart_item.cart_id)
        if cart is None:
            raise CartItemNotFoundError
        if cart.user_id != user.id:
            raise CartItemAccessDeniedError

        product = await product_repository.get_by_id(session=session, product_id=cart_item.product_id)
        if product is None or not product.is_active or product.is_deleted:
            raise CartProductNotFoundError
        if not product.is_available:
            raise CartProductUnavailableError

        stock_service.validate_quantity(product=product, quantity=quantity)
        stock_service.check_available_stock(product=product, quantity=quantity)
        await cart_item_repository.update_quantity(
            session=session,
            cart_item=cart_item,
            product=product,
            quantity=quantity,
        )

        response = await self.recalculate_current_cart(
            session=session,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            cart=cart,
        )
        await cart_cache_service.invalidate_cart(redis_service=redis_service, user_id=user.id)
        return response

    async def add_item(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        cart_cache_service: CartCacheService,
        cart_repository: CartRepository,
        cart_item_repository: CartItemRepository,
        product_repository: ProductRepository,
        promo_code_repository: PromoCodeRepository,
        cart_calculator_service: CartCalculatorService,
        stock_service: StockService,
        user,
        product_id: int,
        quantity: Decimal,
    ) -> DetailedCartResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        product = await product_repository.get_by_id(session=session, product_id=product_id)
        if product is None:
            raise CartProductNotFoundError
        if not product.is_active or product.is_deleted:
            raise CartProductNotFoundError
        if not product.is_available:
            raise CartProductUnavailableError

        stock_service.validate_quantity(product=product, quantity=quantity)

        cart = await self.get_or_create_cart(
            session=session,
            cart_repository=cart_repository,
            user_id=user.id,
        )
        cart_item = await cart_item_repository.get_by_cart_and_product_id(
            session=session,
            cart_id=cart.id,
            product_id=product.id,
        )
        final_quantity = quantity if cart_item is None else cart_item.quantity + quantity
        stock_service.check_available_stock(product=product, quantity=final_quantity)

        if cart_item is None:
            await cart_item_repository.create(
                session=session,
                cart_id=cart.id,
                product=product,
                quantity=final_quantity,
            )
        else:
            await cart_item_repository.update_quantity(
                session=session,
                cart_item=cart_item,
                product=product,
                quantity=final_quantity,
            )

        response = await self.recalculate_current_cart(
            session=session,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            cart=cart,
        )
        await cart_cache_service.invalidate_cart(redis_service=redis_service, user_id=user.id)
        return response

    async def get_current_cart(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        cart_cache_service: CartCacheService,
        cart_repository: CartRepository,
        cart_item_repository: CartItemRepository,
        product_repository: ProductRepository,
        promo_code_repository: PromoCodeRepository,
        cart_calculator_service: CartCalculatorService,
        user,
    ) -> DetailedCartResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cached_cart = await cart_cache_service.get_cart(redis_service=redis_service, user_id=user.id)
        if cached_cart is not None:
            return cached_cart

        cart = await self.get_or_create_cart(
            session=session,
            cart_repository=cart_repository,
            user_id=user.id,
        )
        response = await self.recalculate_current_cart(
            session=session,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            cart=cart,
        )
        await cart_cache_service.set_cart(
            redis_service=redis_service,
            user_id=user.id,
            response=response,
            ttl_seconds=settings.cart.cache_ttl_seconds,
        )
        return response

    async def get_or_create_cart(
        self,
        *,
        session: AsyncSession,
        cart_repository: CartRepository,
        user_id: int,
    ) -> Cart:
        return await cart_repository.get_or_create_by_user_id(session=session, user_id=user_id)

    async def apply_promo_code(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        cart_cache_service: CartCacheService,
        cart_repository: CartRepository,
        cart_item_repository: CartItemRepository,
        product_repository: ProductRepository,
        promo_code_repository: PromoCodeRepository,
        promo_code_usage_repository: PromoCodeUsageRepository,
        cart_calculator_service: CartCalculatorService,
        promo_code_service: PromoCodeService,
        user,
        code: str,
    ) -> DetailedCartResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cart = await self.get_or_create_cart(
            session=session,
            cart_repository=cart_repository,
            user_id=user.id,
        )
        cart_items = await cart_item_repository.get_by_cart_id(session=session, cart_id=cart.id)
        if not cart_items:
            raise CartEmptyError

        promo_code = await promo_code_repository.get_by_code(session=session, code=code)
        if promo_code is None:
            raise CartPromoCodeNotFoundError

        products = await product_repository.get_by_ids(
            session=session,
            product_ids=[cart_item.product_id for cart_item in cart_items],
        )
        products_by_id = {product.id: product for product in products}
        base_response = cart_calculator_service.calculate(
            cart_id=cart.id,
            cart_items=cart_items,
            products_by_id=products_by_id,
        )
        total_usage_count = await promo_code_usage_repository.count_by_code(session=session, promo_code_id=promo_code.id)
        user_usage_count = await promo_code_usage_repository.count_by_user_and_code(
            session=session,
            user_id=user.id,
            promo_code_id=promo_code.id,
        )
        promo_code_service.validate_promo_code(
            promo_code=promo_code,
            cart=cart,
            cart_items=cart_items,
            products_by_id=products_by_id,
            subtotal=base_response.final_price,
            total_usage_count=total_usage_count,
            user_usage_count=user_usage_count,
        )
        await cart_repository.set_promo_code(session=session, cart=cart, promo_code_id=promo_code.id)
        promo_discount_amount = promo_code_service.calculate_discount(
            promo_code=promo_code,
            amount=base_response.final_price,
        )
        response = cart_calculator_service.calculate(
            cart_id=cart.id,
            cart_items=cart_items,
            products_by_id=products_by_id,
            promo_code=promo_code,
            promo_discount_amount=promo_discount_amount,
        )
        await cart_cache_service.invalidate_cart(redis_service=redis_service, user_id=user.id)
        return response

    async def remove_promo_code(
        self,
        *,
        session: AsyncSession,
        redis_service: RedisService,
        cart_cache_service: CartCacheService,
        cart_repository: CartRepository,
        cart_item_repository: CartItemRepository,
        product_repository: ProductRepository,
        promo_code_repository: PromoCodeRepository,
        cart_calculator_service: CartCalculatorService,
        user,
    ) -> DetailedCartResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cart = await self.get_or_create_cart(
            session=session,
            cart_repository=cart_repository,
            user_id=user.id,
        )
        if cart.promo_code_id is not None:
            await cart_repository.clear_promo_code(session=session, cart=cart)
        response = await self.recalculate_current_cart(
            session=session,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            cart=cart,
        )
        await cart_cache_service.invalidate_cart(redis_service=redis_service, user_id=user.id)
        return response

    async def clear_cart(
        self,
        *,
        session: AsyncSession,
        cart_item_repository: CartItemRepository,
        cart: Cart,
    ) -> None:
        await cart_item_repository.delete_by_cart_id(session=session, cart_id=cart.id)

    async def add_product_to_cart(
        self,
        *,
        session: AsyncSession,
        cart_item_repository: CartItemRepository,
        cart: Cart,
        product: Product,
        quantity: Decimal,
    ) -> None:
        await cart_item_repository.create_or_update(
            session=session,
            cart_id=cart.id,
            product=product,
            quantity=quantity,
        )

    async def recalculate_cart(
        self,
        *,
        session: AsyncSession,
        cart_item_repository: CartItemRepository,
        cart: Cart,
    ) -> CartResponse:
        items = await cart_item_repository.get_by_cart_id(session=session, cart_id=cart.id)
        total_price, discount_amount, final_price = calculate_cart_totals(items)
        return CartResponse(
            id=cart.id,
            items=[
                CartItemResponse(
                    id=item.id,
                    product_id=item.product_id,
                    name=item.name,
                    quantity=item.quantity,
                    unit=item.unit,
                    price=item.price,
                    total_price=item.total_price,
                )
                for item in items
            ],
            total_price=total_price,
            discount_amount=discount_amount,
            final_price=final_price,
        )

    async def recalculate_current_cart(
        self,
        *,
        session: AsyncSession,
        cart_item_repository: CartItemRepository,
        product_repository: ProductRepository,
        promo_code_repository: PromoCodeRepository,
        cart_calculator_service: CartCalculatorService,
        cart: Cart,
    ) -> DetailedCartResponse:
        cart_items = await cart_item_repository.get_by_cart_id(session=session, cart_id=cart.id)
        products = await product_repository.get_by_ids(
            session=session,
            product_ids=[cart_item.product_id for cart_item in cart_items],
        )
        promo_code = None
        promo_discount_amount = Decimal("0")
        if cart.promo_code_id is not None:
            promo_code = await promo_code_repository.get_by_id(session=session, promo_code_id=cart.promo_code_id)
            if promo_code is not None:
                subtotal_response = cart_calculator_service.calculate(
                    cart_id=cart.id,
                    cart_items=cart_items,
                    products_by_id={product.id: product for product in products},
                )
                promo_discount_amount = PromoCodeService().calculate_discount(
                    promo_code=promo_code,
                    amount=subtotal_response.final_price,
                )

        return cart_calculator_service.calculate(
            cart_id=cart.id,
            cart_items=cart_items,
            products_by_id={product.id: product for product in products},
            promo_code=promo_code,
            promo_discount_amount=promo_discount_amount,
        )
