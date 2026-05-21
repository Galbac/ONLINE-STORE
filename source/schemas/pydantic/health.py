from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str | None = None
    environment: str | None = None


class HealthDbResponse(BaseModel):
    status: str
    database: str
    latency_ms: int | None = None
    message: str | None = None


class HealthStorageResponse(BaseModel):
    status: str
    storage_type: str
    readable: bool | None = None
    writable: bool | None = None
    available: bool | None = None
    latency_ms: int | None = None
    message: str | None = None
