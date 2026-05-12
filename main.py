from contextlib import asynccontextmanager

from dishka.integrations import fastapi as fastapi_integration
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from source.api.routers.http import router as http_router
from source.config.logging import setup_app_logging, setup_uvicorn_logging
from source.config.settings import settings
from source.db.db_helper import db_helper
from source.ioc import setup_di


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await db_helper.dispose()
    await app.state.dishka_container.close()


def create_app() -> FastAPI:
    container = setup_di()
    setup_app_logging()
    setup_uvicorn_logging()
    app = FastAPI(
        title=settings.names.title,
        lifespan=lifespan,
    )
    app.include_router(http_router)
    fastapi_integration.setup_dishka(container, app)
    return app


app = create_app()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.errors()},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
