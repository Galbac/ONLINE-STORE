from secrets import compare_digest

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import Settings, settings
from source.schemas.pydantic.health import HealthDbResponse, HealthOneCResponse, HealthResponse, HealthStorageResponse
from source.services.health_cache import HealthCacheService
from source.services.health import HealthService
from source.services.one_c import OneCIntegrationService
from source.services.redis import RedisService
from source.services.storage import StorageService
from source.utils.health import DatabaseHealthChecker

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, response_model_exclude_none=True, status_code=status.HTTP_200_OK)
async def get_health() -> HealthResponse:
    return HealthService().get_health(config=settings)


@router.get("/health/db", response_model=HealthDbResponse, response_model_exclude_none=True)
@inject
async def get_db_health(
    authorization: str | None = Header(default=None),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    session: FromDishka[AsyncSession] = None,
    config: FromDishka[Settings] = None,
    health_service: FromDishka[HealthService] = None,
    database_health_checker: FromDishka[DatabaseHealthChecker] = None,
):
    verify_internal_health_token(
        config=config,
        authorization=authorization,
        x_internal_token=x_internal_token,
    )
    try:
        return await health_service.check_db(
            session=session,
            config=config,
            database_health_checker=database_health_checker,
        )
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "database": "postgresql",
                "message": "Database unavailable",
            },
        )


@router.get("/health/storage", response_model=HealthStorageResponse, response_model_exclude_none=True)
@inject
async def get_storage_health(
    authorization: str | None = Header(default=None),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    config: FromDishka[Settings] = None,
    health_service: FromDishka[HealthService] = None,
    storage_service: FromDishka[StorageService] = None,
):
    verify_internal_health_token(
        config=config,
        authorization=authorization,
        x_internal_token=x_internal_token,
    )
    storage_type = getattr(config.media, "storage", "unknown")
    try:
        return await health_service.check_storage(
            config=config,
            storage_service=storage_service,
        )
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "storage_type": storage_type,
                "message": "Storage unavailable",
            },
        )


@router.get("/health/1c", response_model=HealthOneCResponse, response_model_exclude_none=True)
@inject
async def get_one_c_health(
    authorization: str | None = Header(default=None),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    config: FromDishka[Settings] = None,
    redis_service: FromDishka[RedisService] = None,
    health_service: FromDishka[HealthService] = None,
    health_cache_service: FromDishka[HealthCacheService] = None,
    one_c_integration_service: FromDishka[OneCIntegrationService] = None,
):
    verify_internal_health_token(
        config=config,
        authorization=authorization,
        x_internal_token=x_internal_token,
    )
    cached_status = await health_cache_service.get_1c_status(redis_service=redis_service)
    if cached_status is not None:
        if cached_status.status == "error":
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=cached_status.model_dump(exclude_none=True),
            )
        return cached_status

    try:
        response = await health_service.check_1c(
            config=config,
            one_c_integration_service=one_c_integration_service,
        )
        await health_cache_service.set_1c_status(
            redis_service=redis_service,
            response=response,
            ttl_seconds=config.app.health_1c_cache_ttl_seconds,
        )
        if response.status == "error":
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=response.model_dump(exclude_none=True),
            )
        return response
    except Exception:
        response = HealthOneCResponse(
            status="error",
            enabled=True,
            available=False,
            message="1C unavailable",
        )
        await health_cache_service.set_1c_status(
            redis_service=redis_service,
            response=response,
            ttl_seconds=config.app.health_1c_cache_ttl_seconds,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(exclude_none=True),
        )


def verify_internal_health_token(
    *,
    config: Settings,
    authorization: str | None,
    x_internal_token: str | None,
) -> None:
    if not config.app.health_protect_internal_endpoints:
        return
    expected_token = config.app.health_internal_token
    token = x_internal_token
    if token is None and authorization is not None:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value
    if not expected_token or not token or not compare_digest(token, expected_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
