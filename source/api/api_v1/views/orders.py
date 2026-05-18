from dishka.integrations.fastapi import FromDishka, inject
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
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
)
from source.errors.delivery import DeliveryTimeSlotUnavailableError
from source.repositories.address import AddressRepository
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.delivery_time_slot import DeliveryTimeSlotRepository
from source.repositories.order import OrderRepository
from source.repositories.order_item import OrderItemRepository
from source.repositories.payment import PaymentRepository
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
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
from source.services.delivery import DeliveryService, DeliveryTimeSlotService
from source.services.delivery_cache import DeliveryCacheService
from source.services.notifications import EmailService, NotificationService, TelegramNotificationService
from source.services.one_c import OneCIntegrationService
from source.services.order import OrderService
from source.services.order_cache import OrderCacheService
from source.services.payment import PaymentService
from source.services.product_cache import ProductCacheService
from source.services.profile_cache import ProfileCacheService
from source.services.promo_code import PromoCodeService
from source.services.redis import RedisService
from source.services.stock import StockService
from source.config.settings import settings

router = APIRouter(tags=["orders"])


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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Заказ принадлежит другому пользователю") from error


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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Заказ принадлежит другому пользователю") from error
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
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Заказ принадлежит другому пользователю") from error


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
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден") from error
    except OrderAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Заказ принадлежит другому пользователю") from error
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
    body: OrderCreateRequest = Body(),
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
) -> OrderCreateResponse:
    try:
        return await order_service.create_order(
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
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except OrderCartNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Корзина не найдена") from error
    except CartEmptyError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Корзина пустая") from error
    except OrderAddressNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Адрес не найден") from error
    except OrderAddressAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Адрес принадлежит другому пользователю") from error
    except OrderPickupPointNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Точка самовывоза не найдена") from error
    except OrderPickupPointInactiveError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Точка самовывоза неактивна") from error
    except DeliveryTimeSlotUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Временной интервал недоступен") from error
    except OrderPromoCodeInvalidError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Промокод больше недействителен") from error
    except OrderUnavailableItemsError as error:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=jsonable_encoder({"detail": "Некоторые товары недоступны", "items": error.items}),
        )
