from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Body, Depends, HTTPException, status
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
    OrderAddressNotFoundError,
    OrderCartNotFoundError,
    OrderPickupPointInactiveError,
    OrderPickupPointNotFoundError,
    OrderPromoCodeInvalidError,
    OrderUnavailableItemsError,
)
from source.repositories.address import AddressRepository
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.order import OrderRepository
from source.repositories.order_item import OrderItemRepository
from source.repositories.payment import PaymentRepository
from source.repositories.pickup_point import PickupPointRepository
from source.repositories.product import ProductRepository
from source.repositories.promo_code import PromoCodeRepository, PromoCodeUsageRepository
from source.schemas.pydantic.order import OrderCreateRequest, OrderCreateResponse
from source.services.cart import CartCalculatorService
from source.services.cart_cache import CartCacheService
from source.services.delivery import DeliveryService
from source.services.notifications import EmailService, NotificationService, TelegramNotificationService
from source.services.one_c import OneCIntegrationService
from source.services.order import OrderService
from source.services.payment import PaymentService
from source.services.product_cache import ProductCacheService
from source.services.profile_cache import ProfileCacheService
from source.services.promo_code import PromoCodeService
from source.services.redis import RedisService
from source.services.stock import StockService

router = APIRouter(tags=["orders"])


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
    payment_service: FromDishka[PaymentService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
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
            payment_service=payment_service,
            cart_cache_service=cart_cache_service,
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
    except OrderPromoCodeInvalidError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Промокод больше недействителен") from error
    except OrderUnavailableItemsError as error:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=jsonable_encoder({"detail": "Некоторые товары недоступны", "items": error.items}),
        )
