from source.config.settings import Settings
from source.schemas.pydantic.health import HealthResponse


class HealthService:
    def get_health(self, *, config: Settings) -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=config.app.name,
            version=config.app.version or None,
            environment=config.app.environment if config.app.health_show_environment else None,
        )
