from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str | None = None
    environment: str | None = None
