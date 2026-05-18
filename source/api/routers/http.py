from fastapi import APIRouter
from source.api.api_v1.views.auth import router as auth_router
from source.api.api_v1.views.cart import router as cart_router
from source.api.api_v1.views.categories import router as categories_router
from source.api.api_v1.views.delivery import router as delivery_router
from source.api.api_v1.views.discounts import router as discounts_router
from source.api.api_v1.views.favorites import router as favorites_router
from source.api.api_v1.views.profile import router as profile_router
from source.api.api_v1.views.products import router as products_router
from source.api.api_v1.views.orders import router as orders_router
from source.api.api_v1.views.payments import router as payments_router
from source.api.api_v1.views.promo_codes import router as promo_codes_router
from source.api.api_v1.views.users import router as users_router
from source.api.api_v1.views.uploads import router as uploads_router
from source.config.settings import settings

router = APIRouter(
    prefix=settings.api.prefix,
)

router.include_router(auth_router)
router.include_router(cart_router)
router.include_router(categories_router)
router.include_router(delivery_router)
router.include_router(discounts_router)
router.include_router(products_router)
router.include_router(orders_router)
router.include_router(payments_router)
router.include_router(promo_codes_router)
router.include_router(users_router)
router.include_router(profile_router)
router.include_router(favorites_router)
router.include_router(uploads_router)
