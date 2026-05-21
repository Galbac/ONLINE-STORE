import asyncio
from time import perf_counter

from source.config.settings import Settings
from source.schemas.pydantic.health import HealthDbResponse, HealthResponse, HealthStorageResponse
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

    async def check_storage(
        self,
        *,
        config: Settings,
        storage_service,
    ) -> HealthStorageResponse:
        started_at = perf_counter()
        result = await asyncio.wait_for(
            storage_service.health_check(check_write=config.app.health_storage_check_write),
            timeout=config.app.health_storage_timeout_seconds,
        )
        latency_ms = int((perf_counter() - started_at) * 1000)
        if config.media.storage == "local":
            return HealthStorageResponse(
                status="ok",
                storage_type="local",
                readable=result.get("readable") is True,
                writable=result.get("writable") if result.get("writable") is not None else None,
            )
        return HealthStorageResponse(
            status="ok",
            storage_type=config.media.storage,
            available=result.get("available") is True,
            latency_ms=latency_ms,
        )
