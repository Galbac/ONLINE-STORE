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
    if getattr(settings.app, "sentry_dsn", None):
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=settings.app.sentry_dsn,
                environment=settings.app.environment,
                traces_sample_rate=0.1,
            )
        except Exception:
            pass

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

    @app.middleware("http")
    async def track_metrics(request, call_next):
        import time
        from source.utils.metrics import metrics_collector
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        metrics_collector.record_request(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
            duration=duration,
        )
        return response

    return app


app = create_app()


def format_pydantic_error_msg(error: dict) -> str:
    msg = str(error.get("msg", ""))
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
    if "Field required" in msg:
        msg = "Поле обязательно для заполнения"
    elif "Input should be a valid integer" in msg:
        msg = "Значение должно быть целым числом"
    elif "Input should be a valid number" in msg:
        msg = "Значение должно быть числом"
    elif "Input should be a valid boolean" in msg:
        msg = "Значение должно быть логическим (true/false)"
    elif "Input should be a valid string" in msg:
        msg = "Значение должно быть строкой"
    elif "Extra inputs are not permitted" in msg:
        msg = "Переданы непредусмотренные поля"
    elif "value is not a valid email address" in msg:
        msg = "Некорректный адрес электронной почты"
    return msg


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request,
    exc: RequestValidationError,
) -> JSONResponse:
    from fastapi.encoders import jsonable_encoder

    cleaned_errors = []
    first_readable_message = None
    for err in exc.errors():
        err_copy = dict(err)
        cleaned_msg = format_pydantic_error_msg(err_copy)
        err_copy["msg"] = cleaned_msg
        if "ctx" in err_copy and isinstance(err_copy["ctx"], dict):
            err_copy["ctx"] = {k: str(v) for k, v in err_copy["ctx"].items()}
        cleaned_errors.append(err_copy)
        if first_readable_message is None:
            loc_items = [str(item) for item in err_copy.get("loc", []) if str(item) and str(item) not in ("body", "query", "path")]
            loc = " -> ".join(loc_items)
            first_readable_message = f"Поле \"{loc}\": {cleaned_msg}" if loc else cleaned_msg

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=jsonable_encoder({
            "detail": cleaned_errors,
            "message": first_readable_message or "Ошибка валидации данных",
        }),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def get_prometheus_metrics():
    from fastapi import Response
    from source.utils.metrics import metrics_collector
    return Response(
        content=metrics_collector.export_prometheus(),
        media_type="text/plain; version=0.0.4",
    )
