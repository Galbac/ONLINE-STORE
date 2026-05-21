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
