from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    InactiveUserError,
    OrderAccessDeniedError,
    OrderAlreadyPaidError,
    OrderPaymentMethodNotOnlineError,
    OrderPaymentStatusNotAllowedError,
    PaymentAccessDeniedError,
    PaymentNotFoundError,
    PaymentProviderCreateError,
)
from source.repositories.order import OrderRepository
from source.repositories.payment import PaymentRepository
from source.schemas.pydantic.payment import PaymentCreateRequest, PaymentCreateResponse, PaymentDetailResponse
from source.services.order import OrderService
from source.services.order_cache import OrderCacheService
from source.services.payment_cache import PaymentCacheService
from source.services.payment import PaymentProviderService, PaymentService
from source.services.redis import RedisService


router = APIRouter(tags=["payments"])


@router.post("/payments/create", response_model=PaymentCreateResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_payment(
    body: PaymentCreateRequest,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    order_service: FromDishka[OrderService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    payment_service: FromDishka[PaymentService] = None,
    payment_provider_service: FromDishka[PaymentProviderService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
) -> PaymentCreateResponse:
    order = await order_repository.get_by_id(session=session, order_id=body.order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")

    try:
        return await payment_service.create_payment(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            order=order,
            order_repository=order_repository,
            payment_repository=payment_repository,
            order_service=order_service,
            payment_provider_service=payment_provider_service,
            order_cache_service=order_cache_service,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except OrderAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Заказ принадлежит другому пользователю") from error
    except OrderPaymentMethodNotOnlineError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заказ не требует онлайн-оплаты") from error
    except OrderAlreadyPaidError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заказ уже оплачен") from error
    except OrderPaymentStatusNotAllowedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Заказ нельзя оплатить в текущем статусе") from error
    except PaymentProviderCreateError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка создания платежа у провайдера") from error


@router.get("/payments/{payment_id}", response_model=PaymentDetailResponse, status_code=status.HTTP_200_OK)
@inject
async def get_payment_detail(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    order_repository: FromDishka[OrderRepository] = None,
    payment_repository: FromDishka[PaymentRepository] = None,
    payment_service: FromDishka[PaymentService] = None,
    payment_provider_service: FromDishka[PaymentProviderService] = None,
    payment_cache_service: FromDishka[PaymentCacheService] = None,
    order_cache_service: FromDishka[OrderCacheService] = None,
) -> PaymentDetailResponse:
    if payment_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный payment_id")
    try:
        return await payment_service.get_payment_detail(
            session=session,
            commiter=commiter,
            redis_service=redis_service,
            user=current_user,
            payment_id=payment_id,
            payment_repository=payment_repository,
            order_repository=order_repository,
            payment_provider_service=payment_provider_service,
            payment_cache_service=payment_cache_service,
            order_cache_service=order_cache_service,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except PaymentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Платёж не найден") from error
    except PaymentAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Платёж принадлежит другому пользователю") from error
