import logging

logger = logging.getLogger("source")


class HealthcheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "/healthcheck" not in msg


def setup_uvicorn_logging():
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.addFilter(HealthcheckFilter())


def _has_handler(logger: logging.Logger, handler_type: type[logging.Handler], level: int) -> bool:
    return any(isinstance(handler, handler_type) and handler.level == level for handler in logger.handlers)


def setup_app_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not _has_handler(root_logger, logging.StreamHandler, logging.INFO):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        root_logger.addHandler(console_handler)

    if not _has_handler(root_logger, logging.FileHandler, logging.WARNING):
        file_handler = logging.FileHandler("/tmp/logger_warning.log")
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        root_logger.addHandler(file_handler)

    logger.setLevel(logging.INFO)
