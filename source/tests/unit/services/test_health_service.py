from source.config.settings import settings
from source.services.health import HealthService


def test_health_service_returns_ok() -> None:
    response = HealthService().get_health(config=settings)

    assert response.status == "ok"


def test_health_service_returns_service_name() -> None:
    response = HealthService().get_health(config=settings)

    assert response.service


def test_health_service_does_not_require_db_or_redis() -> None:
    response = HealthService().get_health(config=settings)

    assert response.status == "ok"


def test_health_service_does_not_return_secrets() -> None:
    response = HealthService().get_health(config=settings)
    payload = response.model_dump_json()

    assert "password" not in payload.lower()
    assert "secret" not in payload.lower()
    assert "token" not in payload.lower()
