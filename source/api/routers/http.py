from fastapi import APIRouter
from source.api.api_v1.views.auth import router as auth_router
from source.api.api_v1.views.profile import router as profile_router
from source.api.api_v1.views.users import router as users_router
from source.config.settings import settings

router = APIRouter(
    prefix=settings.api.prefix,
)

router.include_router(auth_router)
router.include_router(users_router)
router.include_router(profile_router)
