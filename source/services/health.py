import asyncio
from time import perf_counter

from source.config.settings import Settings
from source.schemas.pydantic.health import HealthDbResponse, HealthResponse
from source.utils.health import DatabaseHealthChecker


class HealthService:
    def get_health(self, *, config: Settings) -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=config.app.name,
            version=config.app.version or None,
            environment=config.app.environment if config.app.health_show_environment else None,
        )

    async def check_db(
        self,
        *,
        session,
        config: Settings,
        database_health_checker: DatabaseHealthChecker,
    ) -> HealthDbResponse:
        started_at = perf_counter()
        await asyncio.wait_for(
            database_health_checker.check(session=session),
            timeout=config.app.health_db_timeout_seconds,
        )
        latency_ms = int((perf_counter() - started_at) * 1000)
        return HealthDbResponse(
            status="ok",
            database="postgresql",
            latency_ms=latency_ms,
        )
