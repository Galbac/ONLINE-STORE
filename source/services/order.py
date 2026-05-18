from decimal import Decimal
from datetime import datetime

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
    OrderAccessDeniedError,
    OrderAlreadyCancelledError,
    OrderCancellationNotAllowedError,
    OrderNotFoundError,
    OrderPaidCancellationRequiresManagerError,
    OrderPickupPointInactiveError,
    OrderPickupPointNotFoundError,
    OrderPromoCodeInvalidError,
    OrderUnavailableItemsError,
)
from source.schemas.pydantic.order import (
    OrderAddressResponse,
    OrderCancelRequest,
    OrderCancelResponse,
    OrderCreateResponse,
    OrderDetailResponse,
    OrderItemResponse,
    OrderMyListQueryParams,
    OrderMyListResponse,
    OrderPaymentResponse,
    OrderPickupPointResponse,
    OrderShortStatusResponse,
)
from source.utils.query_hash import build_query_hash
from source.utils.order import calculate_order_totals, generate_order_number, is_order_cancel_allowed


class OrderService:
    async def cancel_order(
        self,
        *,
        session,
        commiter,
        redis_service,
        user,
        order_id: int,
        data: OrderCancelRequest,
        order_repository,
        order_item_repository,
        product_repository,
        promo_code_usage_repository,
        payment_repository,
        stock_service,
        promo_code_service,
        payment_service,
        order_cache_service,
        profile_cache_service,
        product_cache_service,
        cart_cache_service,
        one_c_integration_service,
        notification_service,
        email_service,
        telegram_service,
    ) -> OrderCancelResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        order = await order_repository.get_by_id(session=session, order_id=order_id)
        if order is None:
            raise OrderNotFoundError
        if order.user_id != user.id:
            raise OrderAccessDeniedError
        if order.status == "cancelled":
            raise OrderAlreadyCancelledError
        if not is_order_cancel_allowed(status=order.status, allowed_statuses=settings.orders.cancel_allowed_statuses):
            raise OrderCancellationNotAllowedError

        payment = await payment_repository.get_by_order_id(session=session, order_id=order.id)
        if (
            order.payment_method == "online"
            and order.payment_status == "paid"
            and not settings.payments.auto_refund_enabled
        ):
            raise OrderPaidCancellationRequiresManagerError

        order_items = await order_item_repository.get_by_order_id(session=session, order_id=order.id)
        products = await product_repository.get_by_ids(
            session=session,
            product_ids=[item.product_id for item in order_items],
        )
        products_by_id = {product.id: product for product in products}

        try:
            await order_repository.update_status(session=session, order=order, status="cancelled")
            order.cancel_reason = data.reason
            order.cancelled_at = datetime.now(settings.tz)
            order.cancelled_by = "customer"
            released_products = await stock_service.release_reserved_items(
                product_repository=product_repository,
                session=session,
                products_by_id=products_by_id,
                order_items=order_items,
            )
            await promo_code_service.cancel_usage(
                promo_code_usage_repository=promo_code_usage_repository,
                session=session,
                order_id=order.id,
            )
            if payment is not None and order.payment_method == "online" and order.payment_status == "paid":
                await payment_service.create_refund_request(order=order)
            await one_c_integration_service.mark_order_cancel_pending_sync(order=order)
            await commiter.commit()
        except Exception:
            await commiter.rollback()
            raise

        await order_cache_service.invalidate_order(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order.id,
        )
        await profile_cache_service.invalidate_orders(redis_service=redis_service, user_id=user.id)
        await profile_cache_service.delete_summary(redis_service=redis_service, user_id=user.id)
        await product_cache_service.invalidate_by_stock_changes(redis_service=redis_service, products=released_products)
        await cart_cache_service.invalidate_summary(redis_service=redis_service, user_id=user.id)
        await notification_service.notify_order_cancelled(
            email_service=email_service,
            telegram_service=telegram_service,
            order=order,
        )
        return OrderCancelResponse(
            message="Заказ отменён",
            order=OrderShortStatusResponse(
                id=order.id,
                order_number=order.order_number,
                status=order.status,
                payment_status=order.payment_status,
                cancel_reason=order.cancel_reason,
                cancelled_at=order.cancelled_at,
            ),
        )

    async def get_order_detail(
        self,
        *,
        session,
        redis_service,
        user,
        order_id: int,
        order_repository,
        order_item_repository,
        address_repository,
        pickup_point_repository,
        payment_repository,
        order_cache_service,
    ) -> OrderDetailResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        cached_order = await order_cache_service.get_detail(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order_id,
        )
        if cached_order is not None:
            return cached_order

        order = await order_repository.get_by_id(session=session, order_id=order_id)
        if order is None:
            raise OrderNotFoundError
        if order.user_id != user.id:
            raise OrderAccessDeniedError

        order_items = await order_item_repository.get_by_order_id(session=session, order_id=order.id)
        address = None
        pickup_point = None
        if order.delivery_type == "delivery" and order.address_id is not None:
            stored_address = await address_repository.get_by_id(session=session, address_id=order.address_id)
            if stored_address is not None:
                address = OrderAddressResponse(
                    id=stored_address.id,
                    city=stored_address.city,
                    street=stored_address.street,
                    house=stored_address.house,
                    apartment=stored_address.apartment,
                    comment=stored_address.comment,
                )
        elif order.delivery_type == "pickup" and order.pickup_point_id is not None:
            stored_pickup_point = await pickup_point_repository.get_by_id(
                session=session,
                pickup_point_id=order.pickup_point_id,
            )
            if stored_pickup_point is not None:
                pickup_point = OrderPickupPointResponse(
                    id=stored_pickup_point.id,
                    name=stored_pickup_point.name,
                )

        payment_record = await payment_repository.get_by_order_id(session=session, order_id=order.id)
        payment = None
        if payment_record is not None:
            payment = OrderPaymentResponse(
                id=payment_record.id,
                amount=payment_record.amount,
                status=payment_record.status,
                payment_url=payment_record.payment_url,
            )

        response = OrderDetailResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            delivery_type=order.delivery_type,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            customer_email=order.customer_email,
            address=address,
            pickup_point=pickup_point,
            payment=payment,
            items=[
                OrderItemResponse(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=item.product_name,
                    product_slug=item.product_slug,
                    quantity=item.quantity,
                    unit=item.unit,
                    product_type=item.product_type,
                    price=item.price,
                    old_price=item.old_price,
                    discount_amount=item.discount_amount,
                    total_price=item.total_price,
                    final_price=item.final_price,
                )
                for item in order_items
            ],
            subtotal=order.subtotal,
            discount_amount=order.discount_amount,
            promo_discount_amount=order.promo_discount_amount,
            delivery_price=order.delivery_price,
            final_price=order.final_price,
            comment=order.comment,
            created_at=order.created_date,
            updated_at=order.updated_date,
        )
        await order_cache_service.set_detail(
            redis_service=redis_service,
            user_id=user.id,
            order_id=order.id,
            response=response,
            ttl_seconds=settings.order_detail.cache_ttl_seconds,
        )
        return response

    async def get_my_orders(
        self,
        *,
        session,
        redis_service,
        user,
        query: OrderMyListQueryParams,
        order_repository,
        order_cache_service,
    ) -> OrderMyListResponse:
        if not user.is_active or user.is_deleted:
            raise InactiveUserError

        query_hash = build_query_hash(query.model_dump())
        cached_orders = await order_cache_service.get_my_orders(
            redis_service=redis_service,
            user_id=user.id,
            query_hash=query_hash,
        )
        if cached_orders is not None:
            return cached_orders

        items = await order_repository.get_by_user_id(
            session=session,
            user_id=user.id,
            query=query,
        )
        total = await order_repository.count_by_user_id(
            session=session,
            user_id=user.id,
            query=query,
        )
        pages = (total + query.limit - 1) // query.limit if total else 0
        response = OrderMyListResponse(
            items=items,
            total=total,
            page=query.page,
            limit=query.limit,
            pages=pages,
        )
        await order_cache_service.set_my_orders(
            redis_service=redis_service,
            user_id=user.id,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.orders_my.cache_ttl_seconds,
        )
        return response

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
        order_cache_service,
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
                    order_id=order.id,
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
        await order_cache_service.invalidate_my_orders(redis_service=redis_service, user_id=user.id)
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
