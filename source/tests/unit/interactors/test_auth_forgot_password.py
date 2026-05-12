import json
import logging

import pytest
from pydantic import ValidationError

from source.db.models.choises.enum import UserRole
from source.db.models.user import User
from source.errors.auth import PasswordResetRateLimitExceededError
from source.interactors.auth_forgot_password import AuthForgotPasswordInteractor
from source.schemas.pydantic.auth import ForgotPasswordRequest
from source.services.auth import AuthService, PASSWORD_RESET_SUCCESS_MESSAGE


class FakeScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, execute_results: list | None = None) -> None:
        self.execute_results = execute_results or []

    async def execute(self, statement):
        value = self.execute_results.pop(0) if self.execute_results else None
        return FakeScalarResult(value)


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value
        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)
        self.ttls.pop(key, None)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, ttl_seconds: int) -> None:
        self.ttls[key] = ttl_seconds


class FakeEmailService:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send_password_reset_email(self, *, email: str, reset_link: str) -> None:
        self.sent.append({"email": email, "reset_link": reset_link})


class FakeTelegramService:
    def __init__(self) -> None:
        self.notifications: list[dict[str, object]] = []

    async def notify_admin_password_reset_issue(self, *, user_id: int, login: str) -> None:
        self.notifications.append({"user_id": user_id, "login": login})


def build_user(
    *,
    email: str | None = "ivan@example.com",
    is_active: bool = True,
) -> User:
    user = User(
        name="Иван Иванов",
        phone="+79990000000",
        email=email,
        password_hash="hash",
        role=UserRole.CUSTOMER,
        is_active=is_active,
    )
    user.id = 1
    return user


async def execute_forgot_password(
    *,
    user: User | None = None,
    login: str = "ivan@example.com",
    redis_service: FakeRedisService | None = None,
    email_service: FakeEmailService | None = None,
    telegram_service: FakeTelegramService | None = None,
) -> tuple:
    auth_service = AuthService()
    redis_service = redis_service or FakeRedisService()
    email_service = email_service or FakeEmailService()
    telegram_service = telegram_service or FakeTelegramService()

    response = await AuthForgotPasswordInteractor().execute(
        session=FakeSession(execute_results=[user]),
        auth_service=auth_service,
        redis_service=redis_service,
        email_service=email_service,
        telegram_service=telegram_service,
        data=ForgotPasswordRequest(login=login),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    return response, redis_service, email_service, telegram_service, auth_service


@pytest.mark.asyncio
async def test_forgot_password_by_email_success(monkeypatch) -> None:
    monkeypatch.setattr("source.services.auth.token_urlsafe", lambda _length: "plain-reset-token")

    response, redis_service, email_service, _, auth_service = await execute_forgot_password(
        user=build_user(),
    )

    token_hash = auth_service.hash_password_reset_token("plain-reset-token")
    assert response.message == PASSWORD_RESET_SUCCESS_MESSAGE
    assert f"password_reset:token:{token_hash}" in redis_service.values
    assert redis_service.values["password_reset:user:1"] == token_hash
    assert email_service.sent[0]["email"] == "ivan@example.com"
    assert email_service.sent[0]["reset_link"].endswith("?token=plain-reset-token")


@pytest.mark.asyncio
async def test_forgot_password_by_phone_success(monkeypatch) -> None:
    monkeypatch.setattr("source.services.auth.token_urlsafe", lambda _length: "plain-reset-token")

    response, redis_service, email_service, _, _ = await execute_forgot_password(
        user=build_user(),
        login="+79990000000",
    )

    assert response.message == PASSWORD_RESET_SUCCESS_MESSAGE
    assert redis_service.values["password_reset:rate:login:+79990000000"] == "1"
    assert email_service.sent


@pytest.mark.asyncio
async def test_forgot_password_user_not_found_returns_neutral_response() -> None:
    response, redis_service, email_service, telegram_service, _ = await execute_forgot_password(user=None)

    assert response.message == PASSWORD_RESET_SUCCESS_MESSAGE
    assert redis_service.values == {}
    assert email_service.sent == []
    assert telegram_service.notifications == []


@pytest.mark.asyncio
async def test_forgot_password_inactive_user_returns_neutral_response() -> None:
    response, redis_service, email_service, telegram_service, _ = await execute_forgot_password(
        user=build_user(is_active=False),
    )

    assert response.message == PASSWORD_RESET_SUCCESS_MESSAGE
    assert redis_service.values == {}
    assert email_service.sent == []
    assert telegram_service.notifications == []


def test_forgot_password_invalid_login_format() -> None:
    with pytest.raises(ValidationError):
        ForgotPasswordRequest(login="wrong-login")


@pytest.mark.asyncio
async def test_plain_reset_token_is_not_stored_in_redis(monkeypatch) -> None:
    monkeypatch.setattr("source.services.auth.token_urlsafe", lambda _length: "plain-reset-token")

    _, redis_service, _, _, _ = await execute_forgot_password(user=build_user())

    stored_data = json.dumps(redis_service.values, ensure_ascii=False)
    assert "plain-reset-token" not in stored_data


@pytest.mark.asyncio
async def test_redis_stores_token_hash_only(monkeypatch) -> None:
    monkeypatch.setattr("source.services.auth.token_urlsafe", lambda _length: "plain-reset-token")

    _, redis_service, _, _, auth_service = await execute_forgot_password(user=build_user())

    token_hash = auth_service.hash_password_reset_token("plain-reset-token")
    assert redis_service.values["password_reset:user:1"] == token_hash
    assert redis_service.values["password_reset:user:1"] != "plain-reset-token"


@pytest.mark.asyncio
async def test_password_reset_redis_keys_have_ttl(monkeypatch) -> None:
    monkeypatch.setattr("source.services.auth.token_urlsafe", lambda _length: "plain-reset-token")

    _, redis_service, _, _, auth_service = await execute_forgot_password(user=build_user())

    token_hash = auth_service.hash_password_reset_token("plain-reset-token")
    assert redis_service.ttls[f"password_reset:token:{token_hash}"] == 1800
    assert redis_service.ttls["password_reset:user:1"] == 1800


@pytest.mark.asyncio
async def test_old_reset_token_is_deleted_on_new_request(monkeypatch) -> None:
    monkeypatch.setattr("source.services.auth.token_urlsafe", lambda _length: "new-plain-token")
    redis_service = FakeRedisService()
    redis_service.values["password_reset:user:1"] = "old-token-hash"
    redis_service.values["password_reset:token:old-token-hash"] = "{}"

    await execute_forgot_password(user=build_user(), redis_service=redis_service)

    assert "password_reset:token:old-token-hash" in redis_service.deleted
    assert "password_reset:user:1" in redis_service.deleted
    assert "password_reset:token:old-token-hash" not in redis_service.values


@pytest.mark.asyncio
async def test_forgot_password_rate_limit_by_login() -> None:
    redis_service = FakeRedisService()
    redis_service.values["password_reset:rate:login:ivan@example.com"] = "3"

    with pytest.raises(PasswordResetRateLimitExceededError):
        await execute_forgot_password(user=build_user(), redis_service=redis_service)


@pytest.mark.asyncio
async def test_forgot_password_rate_limit_by_ip() -> None:
    redis_service = FakeRedisService()
    redis_service.values["password_reset:rate:ip:127.0.0.1"] = "10"

    with pytest.raises(PasswordResetRateLimitExceededError):
        await execute_forgot_password(user=build_user(), redis_service=redis_service)


@pytest.mark.asyncio
async def test_email_is_sent_when_user_has_email(monkeypatch) -> None:
    monkeypatch.setattr("source.services.auth.token_urlsafe", lambda _length: "plain-reset-token")

    _, _, email_service, telegram_service, _ = await execute_forgot_password(user=build_user())

    assert email_service.sent[0]["email"] == "ivan@example.com"
    assert telegram_service.notifications == []


@pytest.mark.asyncio
async def test_reset_token_is_not_logged(monkeypatch, caplog) -> None:
    monkeypatch.setattr("source.services.auth.token_urlsafe", lambda _length: "plain-reset-token")

    with caplog.at_level(logging.INFO):
        await execute_forgot_password(user=build_user())

    assert "plain-reset-token" not in caplog.text
