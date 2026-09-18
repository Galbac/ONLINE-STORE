from contextlib import asynccontextmanager

from dishka.integrations import fastapi as fastapi_integration
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from source.api.routers.http import router as http_router
from source.config.logging import setup_app_logging, setup_uvicorn_logging
from source.config.settings import settings
from source.db.db_helper import db_helper
from source.ioc import setup_di


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        settings.media.root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    yield
    await db_helper.dispose()
    await app.state.dishka_container.close()


class CachedStaticFiles(StaticFiles):
    def is_not_modified(self, response_headers, request_headers) -> bool:
        return super().is_not_modified(response_headers, request_headers)

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def create_app() -> FastAPI:
    container = setup_di()
    setup_app_logging()
    setup_uvicorn_logging()
    app = FastAPI(
        title=settings.names.title,
        lifespan=lifespan,
    )
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.middleware.cors_origins,
        allow_credentials=settings.middleware.allow_credentials,
        allow_methods=settings.middleware.allow_methods,
        allow_headers=settings.middleware.allow_headers,
    )
    try:
        settings.media.root.mkdir(parents=True, exist_ok=True)
        app.mount(settings.media.url, CachedStaticFiles(directory=str(settings.media.root)), name="media")
    except OSError:
        import tempfile
        from pathlib import Path
        fallback_dir = Path(tempfile.gettempdir()) / "grocery_media"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        app.mount(settings.media.url, CachedStaticFiles(directory=str(fallback_dir)), name="media")
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
