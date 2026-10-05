from dishka.integrations.fastapi import FromDishka, inject
from datetime import date, datetime
from decimal import Decimal
import hashlib
from sqlalchemy import select, text
from source.db.models.order import Order

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from source.errors.auth import OrderPriceChangedError
from source.api.dependencies import select_store_context
from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.config.settings import settings
from source.db.models.user import User
from source.errors.auth import (
    CartEmptyError,
    InactiveUserError,
    OrderAddressAccessDeniedError,
    OrderAlreadyCancelledError,
    OrderCancellationNotAllowedError,
    OrderAddressNotFoundError,
    OrderCartNotFoundError,
    OrderAccessDeniedError,
    OrderNotFoundError,
    OrderPickupPointInactiveError,
    OrderPickupPointNotFoundError,
    OrderPromoCodeInvalidError,
    OrderPaidCancellationRequiresManagerError,
    OrderUnavailableItemsError,
    OrderItemsNotFoundError,
    RepeatOrderUnavailableError,
    PhoneVerificationRequiredError,
)
from source.errors.delivery import (
    DeliveryMinOrderAmountError,
    DeliveryTimeSlotUnavailableError,
)
from source.repositories.address import AddressRepository
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.delivery_time_slot import DeliveryTimeSlotRepository
from source.repositories.loyalty import LoyaltyRepository
from source.repositories.order import OrderRepository
from source.repositories.order_item import OrderItemRepository
from source.repositories.order_status_history import OrderStatusHistoryRepository
from source.repositories.payment import PaymentRepository
from source.repositories.notification import NotificationRepository
from source.repositories.push_subscription import PushSubscriptionRepository
from source.repositories.pickup_point import PickupPointRepository
from source.repositories.product import ProductRepository
from source.repositories.promo_code import PromoCodeRepository, PromoCodeUsageRepository
from source.schemas.pydantic.order import (
    OrderCreateRequest,
    OrderCreateResponse,
    OrderCancelRequest,
    OrderCancelResponse,
    OrderDetailResponse,
    OrderMyListQueryParams,
    OrderMyListResponse,
    OrderStatusResponse,
    RepeatOrderRequest,
    RepeatOrderResponse,
)
from source.schemas.pydantic.order_tracking import OrderTrackingResponse
from source.schemas.pydantic.receipt import OrderReceiptResponse
from source.services.order_tracking import OrderTrackingService
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
from source.services.delivery import DeliveryService, DeliveryTimeSlotService
from source.services.delivery_cache import DeliveryCacheService
from source.services.loyalty import LoyaltyService
from source.services.notifications import (
    EmailService,
    NotificationService,
    TelegramNotificationService,
)
from source.services.one_c import OneCIntegrationService
from source.services.store_catalog import StoreCatalogService
from source.services.order import OrderService
from source.services.order_cache import OrderCacheService
from source.services.payment import PaymentService
from source.services.product_cache import ProductCacheService
from source.services.profile_cache import ProfileCacheService
from source.services.promo_code import PromoCodeService
from source.services.redis import RedisService
from source.services.stock import StockService
from source.services.web_push import WebPushService

router = APIRouter(tags=["orders"], dependencies=[Depends(select_store_context)])


@router.get("/orders/my", response_model=OrderMyListResponse, status_code=status.HTTP_200_OK)
@inject
async def get_my_orders(
    current_user: User = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status", max_length=50),
    payment_status: str | None = Query(default=None, max_length=50),
    delivery_type: str | None = Query(default=None, pattern="^(delivery|pickup)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=settings.orders_my.default_limit, ge=1, le=settings.orders_my.max_limit),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    order_service: FromDishka[OrderService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
) -> OrderMyListResponse:
    try:
        return await order_service.get_my_orders(
            session=session,
            redis_service=redis_service,
            user=current_user,
            query=OrderMyListQueryParams(
                status=status_filter,
                payment_status=payment_status,
                delivery_type=delivery_type,
                date_from=date_from,
                date_to=date_to,
                page=page,
                limit=limit,
            ),
            order_repository=order_repository,
            order_cache_service=order_cache_service,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error


@router.get("/orders/{order_id}/status", response_model=OrderStatusResponse, status_code=status.HTTP_200_OK)
@inject
async def get_order_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    order_service: FromDishka[OrderService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
) -> OrderStatusResponse:
    if order_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный order_id")
    try:
        return await order_service.get_order_status(
            session=session,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            order_repository=order_repository,
            order_cache_service=order_cache_service,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error


@router.get("/orders/{order_id}/tracking", response_model=OrderTrackingResponse, status_code=status.HTTP_200_OK)
@inject
async def get_order_tracking(
    order_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_status_history_repository: FromDishka[OrderStatusHistoryRepository] = None,
    order_tracking_service: FromDishka[OrderTrackingService] = None,
) -> OrderTrackingResponse:
    if order_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный order_id")
    tracking = await order_tracking_service.get_tracking(
        session=session,
        order_repository=order_repository,
        order_status_history_repository=order_status_history_repository,
        user=current_user,
        order_id=order_id,
    )
    if tracking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    return tracking


@router.get("/orders/{order_id}/receipt", response_model=OrderReceiptResponse, status_code=status.HTTP_200_OK)
@inject
async def get_order_receipt(
    order_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    order_repository: FromDishka[OrderRepository] = None,
) -> OrderReceiptResponse:
    if order_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный order_id")
    order = await order_repository.get_by_id(session=session, order_id=order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    if order.user_id != current_user.id and current_user.role == "customer":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")

    return OrderReceiptResponse(
        order_id=order.id,
        order_number=order.order_number,
        available=False,
        message="Для этого заказа нет данных о фискальном чеке. Если заказ оплачен, обратитесь в поддержку магазина.",
    )


@router.post("/orders/{order_id}/repeat", response_model=RepeatOrderResponse, status_code=status.HTTP_200_OK)
@inject
async def repeat_order(
    order_id: int,
    body: RepeatOrderRequest = Body(default_factory=RepeatOrderRequest),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    order_service: FromDishka[OrderService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
) -> RepeatOrderResponse:
    if order_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный order_id")
    try:
        return await order_service.repeat_order(
            session=session,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            data=body,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            product_repository=product_repository,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            promo_code_repository=promo_code_repository,
            cart_service=cart_service,
            cart_cache_service=cart_cache_service,
            cart_calculator_service=cart_calculator_service,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderItemsNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="В заказе нет товаров") from error
    except RepeatOrderUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Все товары из заказа недоступны для повторения") from error


@router.get("/orders/{order_id}", response_model=OrderDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def get_order_detail(
    order_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    order_service: FromDishka[OrderService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    product_repository: FromDishka[ProductRepository] = None,
) -> OrderDetailResponse:
    if order_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный order_id")
    try:
        return await order_service.get_order_detail(
            session=session,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            address_repository=address_repository,
            pickup_point_repository=pickup_point_repository,
            payment_repository=payment_repository,
            order_cache_service=order_cache_service,
            product_repository=product_repository,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error


@router.post("/orders/{order_id}/cancel", response_model=OrderCancelResponse, status_code=status.HTTP_200_OK)
@inject
async def cancel_order(
    order_id: int,
    body: OrderCancelRequest = Body(default_factory=OrderCancelRequest),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    order_service: FromDishka[OrderService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_usage_repository: FromDishka[PromoCodeUsageRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    stock_service: FromDishka[StockService] = None,
    promo_code_service: FromDishka[PromoCodeService] = None,
    payment_service: FromDishka[PaymentService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    one_c_integration_service: FromDishka[OneCIntegrationService] = None,
    notification_service: FromDishka[NotificationService] = None,
    email_service: FromDishka[EmailService] = None,
    telegram_service: FromDishka[TelegramNotificationService] = None,
    notification_repository: FromDishka[NotificationRepository] = None,
    push_subscription_repository: FromDishka[PushSubscriptionRepository] = None,
    web_push_service: FromDishka[WebPushService] = None,
) -> OrderCancelResponse:
    if order_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный order_id")
    try:
        return await order_service.cancel_order(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            order_id=order_id,
            data=body,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            product_repository=product_repository,
            promo_code_usage_repository=promo_code_usage_repository,
            payment_repository=payment_repository,
            stock_service=stock_service,
            promo_code_service=promo_code_service,
            payment_service=payment_service,
            order_cache_service=order_cache_service,
            profile_cache_service=profile_cache_service,
            product_cache_service=product_cache_service,
            cart_cache_service=cart_cache_service,
            one_c_integration_service=one_c_integration_service,
            notification_service=notification_service,
            email_service=email_service,
            telegram_service=telegram_service,
            notification_repository=notification_repository,
            push_subscription_repository=push_subscription_repository,
            web_push_service=web_push_service,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAlreadyCancelledError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заказ уже отменён") from error
    except OrderCancellationNotAllowedError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заказ нельзя отменить на текущем статусе") from error
    except OrderPaidCancellationRequiresManagerError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Заказ оплачен, требуется возврат через менеджера",
        ) from error


@router.post("/orders", response_model=OrderCreateResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_order(
    request: Request,
    body: OrderCreateRequest = Body(),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    order_service: FromDishka[OrderService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    address_repository: FromDishka[AddressRepository] = None,
    pickup_point_repository: FromDishka[PickupPointRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    promo_code_usage_repository: FromDishka[PromoCodeUsageRepository] = None,
    order_repository: FromDishka[OrderRepository] = None,
    order_item_repository: FromDishka[OrderItemRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    stock_service: FromDishka[StockService] = None,
    promo_code_service: FromDishka[PromoCodeService] = None,
    delivery_service: FromDishka[DeliveryService] = None,
    delivery_cache_service: FromDishka[DeliveryCacheService] = None,
    delivery_time_slot_service: FromDishka[DeliveryTimeSlotService] = None,
    delivery_time_slot_repository: FromDishka[DeliveryTimeSlotRepository] = None,
    payment_service: FromDishka[PaymentService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
    profile_cache_service: FromDishka[ProfileCacheService] = None,
    product_cache_service: FromDishka[ProductCacheService] = None,
    one_c_integration_service: FromDishka[OneCIntegrationService] = None,
    notification_service: FromDishka[NotificationService] = None,
    email_service: FromDishka[EmailService] = None,
    telegram_service: FromDishka[TelegramNotificationService] = None,
    notification_repository: FromDishka[NotificationRepository] = None,
    push_subscription_repository: FromDishka[PushSubscriptionRepository] = None,
    web_push_service: FromDishka[WebPushService] = None,
    loyalty_repository: FromDishka[LoyaltyRepository] = None,
    loyalty_service: FromDishka[LoyaltyService] = None,
) -> OrderCreateResponse:
    request_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    if idempotency_key:
        if len(idempotency_key) > 128:
            raise HTTPException(status_code=400, detail="Слишком длинный ключ оформления заказа")
        lock_key = int.from_bytes(
            hashlib.sha256(f"order:{current_user.id}:{idempotency_key}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        existing_order = await session.scalar(
            select(Order).where(
                Order.user_id == current_user.id,
                Order.idempotency_key == idempotency_key,
            )
        )
        if existing_order:
            if existing_order.request_hash != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Этот ключ уже использован для другого заказа",
                )
            payment = await payment_repository.get_by_order_id(session=session, order_id=existing_order.id)
            return OrderCreateResponse(
                id=existing_order.id,
                order_number=existing_order.order_number,
                status=existing_order.status,
                payment_method=existing_order.payment_method,
                payment_status=existing_order.payment_status,
                delivery_type=existing_order.delivery_type,
                subtotal=existing_order.subtotal,
                discount_amount=existing_order.discount_amount,
                promo_discount_amount=existing_order.promo_discount_amount,
                delivery_price=existing_order.delivery_price,
                final_price=existing_order.final_price,
                payment_url=payment.payment_url if payment else None,
                created_at=existing_order.created_date,
            )

    # 2. Валидация корзины и минимальной суммы в контроллере
    if cart_repository is not None and cart_item_repository is not None:
        cart = await cart_repository.get_by_user_id(session=session, user_id=current_user.id)
        if cart is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Корзина не найдена")
        cart_items = await cart_item_repository.get_by_cart_id(session=session, cart_id=cart.id)
        if not cart_items or len(cart_items) == 0:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"code": "EMPTY_CART", "detail": "Корзина пустая"},
            )
        if product_repository is not None:
            products = await product_repository.get_by_ids(
                session=session,
                product_ids=[item.product_id for item in cart_items],
            )
            products = await StoreCatalogService().scope_products(
                session=session,
                products=products,
                store_id=cart.store_id,
            )
            products_by_id = {p.id: p for p in products}
            items_total = sum(
                (
                    products_by_id[item.product_id].price * item.quantity
                    for item in cart_items
                    if item.product_id in products_by_id
                    and products_by_id[item.product_id].is_available
                    and products_by_id[item.product_id].is_active
                    and not products_by_id[item.product_id].is_deleted
                ),
                Decimal("0"),
            )
            if items_total < Decimal("1000.00"):
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={
                        "code": "MIN_ORDER_AMOUNT_NOT_MET",
                        "detail": "Минимальная сумма заказа для оформления — 1 000 ₽",
                        "min_amount": 1000,
                        "current_amount": float(items_total),
                    },
                )

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        response = await order_service.create_order(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            data=body,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            address_repository=address_repository,
            pickup_point_repository=pickup_point_repository,
            promo_code_repository=promo_code_repository,
            promo_code_usage_repository=promo_code_usage_repository,
            order_repository=order_repository,
            order_item_repository=order_item_repository,
            payment_repository=payment_repository,
            cart_calculator_service=cart_calculator_service,
            stock_service=stock_service,
            promo_code_service=promo_code_service,
            delivery_service=delivery_service,
            delivery_cache_service=delivery_cache_service,
            delivery_time_slot_service=delivery_time_slot_service,
            delivery_time_slot_repository=delivery_time_slot_repository,
            payment_service=payment_service,
            cart_cache_service=cart_cache_service,
            order_cache_service=order_cache_service,
            profile_cache_service=profile_cache_service,
            product_cache_service=product_cache_service,
            one_c_integration_service=one_c_integration_service,
            notification_service=notification_service,
            email_service=email_service,
            telegram_service=telegram_service,
            notification_repository=notification_repository,
            push_subscription_repository=push_subscription_repository,
            web_push_service=web_push_service,
            loyalty_service=loyalty_service,
            loyalty_repository=loyalty_repository,
            user_ip=client_ip,
            user_agent=user_agent,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            accepted_terms_version="1.0",
            accepted_at=datetime.now(settings.tz),
        )

        return response
    except InactiveUserError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или удалён",
        ) from error
    except PhoneVerificationRequiredError:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "code": "PHONE_VERIFICATION_REQUIRED",
                "detail": "Для оплаты при получении требуется подтверждение номера телефона",
            },
        )
    except OrderCartNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Корзина не найдена") from error
    except CartEmptyError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "EMPTY_CART", "detail": "Корзина пустая"},
        )
    except DeliveryMinOrderAmountError:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "MIN_ORDER_AMOUNT_NOT_MET",
                "detail": "Минимальная сумма заказа для оформления — 1 000 ₽",
            },
        )
    except OrderAddressNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Адрес не найден") from error
    except OrderAddressAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Адрес не найден") from error
    except OrderPickupPointNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Точка самовывоза не найдена") from error
    except OrderPickupPointInactiveError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Точка самовывоза неактивна") from error
    except DeliveryTimeSlotUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Временной интервал недоступен") from error
    except OrderPriceChangedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Цены в выбранном магазине изменились. Обновите корзину и подтвердите заказ заново",
        ) from error
    except OrderPromoCodeInvalidError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Промокод больше недействителен",
        ) from error
    except OrderUnavailableItemsError as error:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=jsonable_encoder({"detail": "Некоторые товары недоступны", "items": error.items}),
        )
