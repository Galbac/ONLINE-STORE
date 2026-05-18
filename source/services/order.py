from decimal import Decimal

from source.config.settings import settings
from source.errors.auth import (
    CartEmptyError,
    CartPromoCodeExpiredError,
    CartPromoCodeInactiveError,
    CartPromoCodeLimitExceededError,
    CartPromoCodeMinAmountError,
    CartPromoCodeNotApplicableError,
    InactiveUserError,
    OrderAddressAccessDeniedError,
    OrderAddressNotFoundError,
    OrderCartNotFoundError,
    OrderPickupPointInactiveError,
    OrderPickupPointNotFoundError,
    OrderPromoCodeInvalidError,
    OrderUnavailableItemsError,
)
from source.schemas.pydantic.order import OrderCreateResponse
from source.utils.order import calculate_order_totals, generate_order_number


class OrderService:
    async def create_order(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        data,
        cart_repository,
        cart_item_repository,
        product_repository,
        address_repository,
        pickup_point_repository,
        promo_code_repository,
        promo_code_usage_repository,
        order_repository,
        order_item_repository,
        payment_repository,
        cart_calculator_service,
        stock_service,
        promo_code_service,
        delivery_service,
        payment_service,
        cart_cache_service,
        profile_cache_service,
        product_cache_service,
        one_c_integration_service,
        notification_service,
        email_service,
        telegram_service,
    ) -> OrderCreateResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cart = await cart_repository.get_by_user_id(session=session, user_id=user.id)
        if cart is None:
            raise OrderCartNotFoundError

        cart_items = await cart_item_repository.get_by_cart_id(session=session, cart_id=cart.id)
        if not cart_items:
            raise CartEmptyError

        products = await product_repository.get_by_ids(
            session=session,
            product_ids=[item.product_id for item in cart_items],
        )
        products_by_id = {product.id: product for product in products}
        unavailable_items = stock_service.validate_order_items(cart_items=cart_items, products_by_id=products_by_id)
        if unavailable_items:
            raise OrderUnavailableItemsError(unavailable_items)

        address_id = None
        pickup_point_id = None
        if data.delivery_type == "delivery":
            address = await address_repository.get_by_id(session=session, address_id=data.address_id)
            if address is None or address.is_deleted:
                raise OrderAddressNotFoundError
            if address.user_id != user.id:
                raise OrderAddressAccessDeniedError
            address_id = address.id
        else:
            pickup_point = await pickup_point_repository.get_by_id(
                session=session,
                pickup_point_id=data.pickup_point_id,
            )
            if pickup_point is None:
                raise OrderPickupPointNotFoundError
            if not pickup_point.is_active:
                raise OrderPickupPointInactiveError
            pickup_point_id = pickup_point.id

        promo_code = None
        promo_discount_amount = Decimal("0")
        preliminary_cart = cart_calculator_service.calculate(
            cart_id=cart.id,
            cart_items=cart_items,
            products_by_id=products_by_id,
        )
        if cart.promo_code_id is not None:
            promo_code = await promo_code_repository.get_by_id(session=session, promo_code_id=cart.promo_code_id)
            if promo_code is None:
                raise OrderPromoCodeInvalidError
            total_usage_count = await promo_code_usage_repository.count_by_code(
                session=session,
                promo_code_id=promo_code.id,
            )
            user_usage_count = await promo_code_usage_repository.count_by_user_and_code(
                session=session,
                user_id=user.id,
                promo_code_id=promo_code.id,
            )
            try:
                promo_code_service.validate_for_order(
                    promo_code=promo_code,
                    cart=cart,
                    cart_items=cart_items,
                    products_by_id=products_by_id,
                    subtotal=preliminary_cart.subtotal,
                    total_usage_count=total_usage_count,
                    user_usage_count=user_usage_count,
                )
            except (
                CartPromoCodeInactiveError,
                CartPromoCodeExpiredError,
                CartPromoCodeLimitExceededError,
                CartPromoCodeMinAmountError,
                CartPromoCodeNotApplicableError,
            ) as error:
                raise OrderPromoCodeInvalidError from error
            promo_discount_amount = promo_code_service.calculate_discount(
                promo_code=promo_code,
                amount=preliminary_cart.subtotal - preliminary_cart.discount_amount,
            )

        cart_snapshot = cart_calculator_service.calculate(
            cart_id=cart.id,
            cart_items=cart_items,
            products_by_id=products_by_id,
            promo_code=promo_code,
            promo_discount_amount=promo_discount_amount,
        )
        delivery_price = delivery_service.calculate_delivery_price(delivery_type=data.delivery_type)
        final_price = calculate_order_totals(
            subtotal=cart_snapshot.subtotal,
            discount_amount=cart_snapshot.discount_amount,
            promo_discount_amount=cart_snapshot.promo_discount_amount,
            delivery_price=delivery_price,
        )

        try:
            order = await order_repository.create(
                session=session,
                user_id=user.id,
                address_id=address_id,
                pickup_point_id=pickup_point_id,
                order_number="TEMP",
                status=settings.orders.online_payment_status if data.payment_method == "online" else settings.orders.default_status,
                payment_method=data.payment_method,
                payment_status="unpaid",
                delivery_type=data.delivery_type,
                delivery_date=data.delivery_date,
                delivery_time_slot_id=data.delivery_time_slot_id,
                delivery_price=delivery_price,
                subtotal=cart_snapshot.subtotal,
                discount_amount=cart_snapshot.discount_amount,
                promo_discount_amount=cart_snapshot.promo_discount_amount,
                final_price=final_price,
                customer_name=data.customer_name,
                customer_phone=data.customer_phone,
                customer_email=str(data.customer_email) if data.customer_email is not None else None,
                comment=data.comment,
                sync_status="pending",
                items_count=len(cart_items),
            )
            order.order_number = generate_order_number(prefix=settings.orders.number_prefix, order_id=order.id)
            await order_item_repository.bulk_create(
                session=session,
                items=[
                    {
                        "order_id": order.id,
                        "product_id": item.product_id,
                        "product_name": products_by_id[item.product_id].name,
                        "product_slug": products_by_id[item.product_id].slug,
                        "price": products_by_id[item.product_id].price,
                        "old_price": products_by_id[item.product_id].old_price,
                        "quantity": item.quantity,
                        "unit": products_by_id[item.product_id].unit,
                        "product_type": products_by_id[item.product_id].product_type,
                        "discount_amount": next(
                            snapshot_item.discount_amount
                            for snapshot_item in cart_snapshot.items
                            if snapshot_item.product_id == item.product_id
                        ),
                        "total_price": next(
                            snapshot_item.total_price
                            for snapshot_item in cart_snapshot.items
                            if snapshot_item.product_id == item.product_id
                        ),
                        "final_price": next(
                            snapshot_item.final_price
                            for snapshot_item in cart_snapshot.items
                            if snapshot_item.product_id == item.product_id
                        ),
                    }
                    for item in cart_items
                ],
            )
            await stock_service.reserve_items(products_by_id=products_by_id, cart_items=cart_items)
            if promo_code is not None:
                await promo_code_service.reserve_usage(
                    promo_code_usage_repository=promo_code_usage_repository,
                    session=session,
                    promo_code_id=promo_code.id,
                    user_id=user.id,
                )
            await cart_item_repository.delete_by_cart_id(session=session, cart_id=cart.id)
            await cart_repository.clear_promo_code(session=session, cart=cart)
            await one_c_integration_service.mark_order_pending_sync(order=order)
            payment_url = None
            if data.payment_method == "online":
                payment_url = await payment_service.create_payment(
                    payment_repository=payment_repository,
                    session=session,
                    order=order,
                )
            await commiter.commit()
        except Exception:
            await commiter.rollback()
            raise

        await cart_cache_service.invalidate_cart(redis_service=redis_service, user_id=user.id)
        await profile_cache_service.invalidate_orders(redis_service=redis_service, user_id=user.id)
        await profile_cache_service.delete_summary(redis_service=redis_service, user_id=user.id)
        await product_cache_service.invalidate_by_stock_changes(redis_service=redis_service, products=products)
        await notification_service.notify_order_created(
            email_service=email_service,
            telegram_service=telegram_service,
            order=order,
        )
        return OrderCreateResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            delivery_type=order.delivery_type,
            subtotal=order.subtotal,
            discount_amount=order.discount_amount,
            promo_discount_amount=order.promo_discount_amount,
            delivery_price=order.delivery_price,
            final_price=order.final_price,
            payment_url=payment_url,
            created_at=order.created_date,
        )
