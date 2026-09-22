from fastapi import APIRouter
from source.api.api_v1.views.admin_auth import router as admin_auth_router
from source.api.api_v1.views.admin_dashboard import router as admin_dashboard_router
from source.api.api_v1.views.auth import router as auth_router
from source.api.api_v1.views.banners import router as banners_router
from source.api.api_v1.views.cart import router as cart_router
from source.api.api_v1.views.categories import router as categories_router
from source.api.api_v1.views.delivery import router as delivery_router
from source.api.api_v1.views.discounts import router as discounts_router
from source.api.api_v1.views.favorites import router as favorites_router
from source.api.api_v1.views.feedback import router as feedback_router
from source.api.api_v1.views.health import router as health_router
from source.api.api_v1.views.integration import router as integration_router
from source.api.api_v1.views.orders import router as orders_router
from source.api.api_v1.views.products import router as products_router
from source.api.api_v1.views.profile import router as profile_router
from source.api.api_v1.views.public_settings import router as public_settings_router
from source.api.api_v1.views.loyalty import router as loyalty_router
from source.api.api_v1.views.notifications import router as notifications_router
from source.api.api_v1.views.push_notifications import router as push_notifications_router
from source.api.api_v1.views.payments import router as payments_router
from source.api.api_v1.views.promo_codes import router as promo_codes_router
from source.api.api_v1.views.reviews import router as reviews_router
from source.api.api_v1.views.staff_ops import router as staff_ops_router
from source.api.api_v1.views.users import router as users_router
from source.api.api_v1.views.legal_documents import router as legal_documents_router
from source.api.api_v1.views.admin_legal_documents import router as admin_legal_documents_router
from source.api.api_v1.views.uploads import router as uploads_router
from source.config.settings import settings

router = APIRouter(
    prefix=settings.api.prefix,
)

router.include_router(auth_router)
router.include_router(health_router)
router.include_router(public_settings_router)
router.include_router(banners_router)
router.include_router(admin_auth_router)
router.include_router(admin_dashboard_router)
router.include_router(cart_router)
router.include_router(categories_router)
router.include_router(delivery_router)
router.include_router(discounts_router)
router.include_router(products_router)
router.include_router(orders_router)
router.include_router(notifications_router)
router.include_router(push_notifications_router)
router.include_router(payments_router)
router.include_router(promo_codes_router)
router.include_router(reviews_router)
router.include_router(feedback_router)
router.include_router(loyalty_router)
router.include_router(staff_ops_router)
router.include_router(users_router)
router.include_router(profile_router)
router.include_router(favorites_router)
router.include_router(uploads_router)
router.include_router(integration_router)
router.include_router(legal_documents_router)
router.include_router(admin_legal_documents_router)
