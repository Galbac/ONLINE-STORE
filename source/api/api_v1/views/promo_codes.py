from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Body, Header, HTTPException, Depends, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from source.api.dependencies import get_current_user, resolve_current_user
from source.common.commiter import Commiter
from source.db.models.user import User
from source.errors.auth import (
    CartEmptyError,
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
from source.schemas.pydantic.promo_code import PromoCodeApplyRequest, PromoCodeApplyResponse, PromoCodeCheckRequest, PromoCodeCheckResponse
from source.services.cart import CartCalculatorService, CartService
from source.services.cart_cache import CartCacheService
from source.services.promo_code import PromoCodeService
from source.services.redis import RedisService

router = APIRouter(tags=["promo-codes"])


@router.post("/promo-codes/check", response_model=PromoCodeCheckResponse, response_model_exclude_none=True, status_code=status.HTTP_200_OK)
@inject
async def check_promo_code(
    body: PromoCodeCheckRequest = Body(),
    authorization: str | None = Header(default=None),
    session: FromDishka[AsyncSession] = None,
    redis_service: FromDishka[RedisService] = None,
    promo_code_service: FromDishka[PromoCodeService] = None,
    promo_code_repository: FromDishka[PromoCodeRepository] = None,
    promo_code_usage_repository: FromDishka[PromoCodeUsageRepository] = None,
) -> PromoCodeCheckResponse:
    try:
        current_user = None
        if authorization:
            current_user = await resolve_current_user(authorization=authorization, session=session, redis_service=redis_service)
        return await promo_code_service.check_promo_code(
            session=session,
            promo_code_repository=promo_code_repository,
            promo_code_usage_repository=promo_code_usage_repository,
            user_id=current_user.id if current_user is not None else None,
            data=body,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверные входные данные") from error
    except CartPromoCodeNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Промокод не найден") from error
    except CartPromoCodeInactiveError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Промокод неактивен") from error
    except CartPromoCodeExpiredError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Срок действия промокода истёк") from error
    except CartPromoCodeLimitExceededError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Лимит использования промокода исчерпан") from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error


@router.post("/promo-codes/apply", response_model=PromoCodeApplyResponse, status_code=status.HTTP_200_OK)
@inject
async def apply_promo_code(
    body: PromoCodeApplyRequest = Body(),
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
) -> PromoCodeApplyResponse:
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
        return PromoCodeApplyResponse(message="Промокод применён", cart=cart)
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Сумма заказа меньше минимальной суммы для промокода") from error
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
    except Exception as error:
        await commiter.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера") from error
