from fastapi import APIRouter, status

from source.config.settings import settings
from source.schemas.pydantic.health import HealthResponse
from source.services.health import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, response_model_exclude_none=True, status_code=status.HTTP_200_OK)
async def get_health() -> HealthResponse:
    return HealthService().get_health(config=settings)
