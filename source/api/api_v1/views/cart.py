from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    CartEmptyError,
    CartInsufficientStockError,
    CartItemAccessDeniedError,
    CartItemNotFoundError,
    CartPieceQuantityMustBeIntegerError,
    CartProductNotFoundError,
    CartProductUnavailableError,
    CartQuantityBelowMinimumError,
    CartQuantityStepError,
    CartPromoCodeAlreadyAppliedError,
    CartPromoCodeExpiredError,
    CartPromoCodeInactiveError,
    CartPromoCodeLimitExceededError,
    CartPromoCodeMinAmountError,
    CartPromoCodeNotApplicableError,
    CartPromoCodeNotFoundError,
    InactiveUserError,
)
from source.repositories.cart import CartRepository
from source.repositories.cart_item import CartItemRepository
from source.repositories.product import ProductRepository
from source.repositories.promo_code import PromoCodeRepository, PromoCodeUsageRepository
from source.schemas.pydantic.cart import ApplyPromoCodeRequest, CartItemCreateRequest, CartItemUpdateRequest, CartResponse, CartSummaryResponse, MessageCartResponse
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
from source.services.redis import RedisService
from source.services.stock import StockService
from source.services.promo_code import PromoCodeService

router = APIRouter(tags=["cart"])


@router.get(
    "/cart/summary",
    response_model=CartSummaryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или удалён."},
    },
)
@inject
async def get_cart_summary(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
) -> CartSummaryResponse:
    try:
        return await cart_service.get_cart_summary(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            user=current_user,
        )
    except InactiveUserError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error


@router.delete(
    "/cart/promo-code",
    response_model=MessageCartResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или удалён."},
    },
)
@inject
async def remove_promo_code(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
) -> MessageCartResponse:
    try:
        cart = await cart_service.remove_promo_code(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            user=current_user,
        )
        await commiter.commit()
        return MessageCartResponse(message="Промокод удалён", cart=cart)
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error


@router.delete(
    "/cart",
    response_model=MessageCartResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или удалён."},
    },
)
@inject
async def clear_cart(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
) -> MessageCartResponse:
    try:
        cart = await cart_service.clear_current_cart(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            user=current_user,
        )
        await commiter.commit()
        return MessageCartResponse(message="Корзина очищена", cart=cart)
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error


@router.delete(
    "/cart/items/{cart_item_id}",
    response_model=MessageCartResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверный cart_item_id."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или позиция чужая."},
        status.HTTP_404_NOT_FOUND: {"description": "Позиция корзины не найдена."},
    },
)
@inject
async def delete_cart_item(
    cart_item_id: int,
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
) -> MessageCartResponse:
    try:
        cart = await cart_service.delete_item(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            user=current_user,
            cart_item_id=cart_item_id,
        )
        await commiter.commit()
        return MessageCartResponse(message="Товар удалён из корзины", cart=cart)
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except CartItemAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Позиция корзины принадлежит другому пользователю") from error
    except CartItemNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Позиция корзины не найдена") from error


@router.patch(
    "/cart/items/{cart_item_id}",
    response_model=MessageCartResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные данные корзины."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или позиция чужая."},
        status.HTTP_404_NOT_FOUND: {"description": "Позиция корзины или товар не найдены."},
        status.HTTP_409_CONFLICT: {"description": "Товар недоступен или недостаточно остатка."},
    },
)
@inject
async def update_cart_item(
    cart_item_id: int,
    body: CartItemUpdateRequest = Body(),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    stock_service: FromDishka[StockService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
) -> MessageCartResponse:
    try:
        cart = await cart_service.update_item_quantity(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            stock_service=stock_service,
            user=current_user,
            cart_item_id=cart_item_id,
            quantity=body.quantity,
        )
        await commiter.commit()
        return MessageCartResponse(message="Количество товара обновлено", cart=cart)
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except CartItemAccessDeniedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Позиция корзины принадлежит другому пользователю") from error
    except CartItemNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Позиция корзины не найдена") from error
    except CartProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except CartProductUnavailableError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Товар недоступен") from error
    except CartInsufficientStockError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Недостаточно товара на складе") from error
    except CartPieceQuantityMustBeIntegerError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для штучного товара количество должно быть целым числом",
        ) from error
    except CartQuantityStepError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество не соответствует шагу товара") from error
    except CartQuantityBelowMinimumError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество меньше минимального") from error


@router.post(
    "/cart/items",
    response_model=MessageCartResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Неверные данные корзины."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или удалён."},
        status.HTTP_404_NOT_FOUND: {"description": "Товар не найден."},
        status.HTTP_409_CONFLICT: {"description": "Товар недоступен или недостаточно остатка."},
    },
)
@inject
async def add_cart_item(
    body: CartItemCreateRequest = Body(),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    stock_service: FromDishka[StockService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
) -> MessageCartResponse:
    try:
        cart = await cart_service.add_item(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            stock_service=stock_service,
            user=current_user,
            product_id=body.product_id,
            quantity=body.quantity,
        )
        await commiter.commit()
        return MessageCartResponse(message="Товар добавлен в корзину", cart=cart)
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except CartProductNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден") from error
    except CartProductUnavailableError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Товар недоступен") from error
    except CartInsufficientStockError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Недостаточно товара на складе") from error
    except CartPieceQuantityMustBeIntegerError as error:
        await commiter.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для штучного товара количество должно быть целым числом",
        ) from error
    except CartQuantityStepError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество не соответствует шагу товара") from error
    except CartQuantityBelowMinimumError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество меньше минимального") from error


@router.get(
    "/cart",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или удалён."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Внутренняя ошибка сервера."},
    },
)
@inject
async def get_cart(
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
) -> CartResponse:
    try:
        return await cart_service.get_current_cart(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            cart_calculator_service=cart_calculator_service,
            user=current_user,
        )
    except InactiveUserError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь заблокирован или удалён",
        ) from error


@router.post(
    "/cart/apply-promo-code",
    response_model=MessageCartResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Промокод нельзя применить."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Пользователь не авторизован."},
        status.HTTP_403_FORBIDDEN: {"description": "Пользователь заблокирован или удалён."},
        status.HTTP_404_NOT_FOUND: {"description": "Промокод не найден."},
        status.HTTP_409_CONFLICT: {"description": "Промокод недоступен."},
    },
)
@inject
async def apply_promo_code(
    body: ApplyPromoCodeRequest = Body(),
    current_user: User = Depends(get_current_user),
    session: FromDishka[AsyncSession] = None,
    commiter: FromDishka[Commiter] = None,
    redis_service: FromDishka[RedisService] = None,
    cart_service: FromDishka[CartService] = None,
    cart_cache_service: FromDishka[CartCacheService] = None,
    cart_calculator_service: FromDishka[CartCalculatorService] = None,
    promo_code_service: FromDishka[PromoCodeService] = None,
    cart_repository: FromDishka[CartRepository] = None,
    cart_item_repository: FromDishka[CartItemRepository] = None,
    product_repository: FromDishka[ProductRepository] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    promo_code_usage_repository: FromDishka[PromoCodeUsageRepository] = None,
) -> MessageCartResponse:
    try:
        cart = await cart_service.apply_promo_code(
            session=session,
            redis_service=redis_service,
            cart_cache_service=cart_cache_service,
            cart_repository=cart_repository,
            cart_item_repository=cart_item_repository,
            product_repository=product_repository,
            promo_code_repository=promo_code_repository,
            promo_code_usage_repository=promo_code_usage_repository,
            cart_calculator_service=cart_calculator_service,
            promo_code_service=promo_code_service,
            user=current_user,
            code=body.code,
        )
        await commiter.commit()
        return MessageCartResponse(message="Промокод применён", cart=cart)
    except InactiveUserError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован или удалён") from error
    except CartEmptyError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Корзина пустая") from error
    except CartPromoCodeNotFoundError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Промокод не найден") from error
    except CartPromoCodeMinAmountError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сумма заказа меньше минимальной суммы для промокода") from error
    except CartPromoCodeNotApplicableError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Промокод нельзя применить к этим товарам") from error
    except CartPromoCodeInactiveError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Промокод неактивен") from error
    except CartPromoCodeExpiredError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Срок действия промокода истёк") from error
    except CartPromoCodeLimitExceededError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Лимит использования промокода исчерпан") from error
    except CartPromoCodeAlreadyAppliedError as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Промокод уже применён") from error
