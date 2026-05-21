from secrets import compare_digest

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from source.config.settings import Settings, settings
from source.schemas.pydantic.health import HealthDbResponse, HealthResponse
from source.services.health import HealthService
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
