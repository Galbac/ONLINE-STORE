import os
from datetime import tzinfo
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class RunConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    production: bool = False


class ProjectName(BaseModel):
    title: str = "Grocery Store API"
    path: str = ""
    slug: str = "grocery_store"


class ApiV1Prefix(BaseModel):
    prefix: str = "/v1"


class ApiPrefix(BaseModel):
    prefix: str = "/api"
    v1: ApiV1Prefix = ApiV1Prefix()


class DbSettings(BaseModel):
    url: str | PostgresDsn | None = None
    test_url: str | PostgresDsn | None = None
    echo: bool = False
    echo_pool: bool = False
    max_overflow: int = 10
    pool_size: int = 5
    naming_convention: dict[str, str] = {
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }

    @staticmethod
    def _read_secret_or_env(
        secret_name: str,
        env_var_name: str,
        default: str = "postgres",
    ) -> str:
        run_secret = Path("/run/secrets") / secret_name
        if secret_name and run_secret.exists() and run_secret.is_file():
            return run_secret.read_text().strip()
        return os.getenv(env_var_name, default)

    @classmethod
    def create_url(
        cls,
        user_secret_name: str,
        password_secret_name: str,
        db_name: Optional[str] = None,
    ) -> str:
        db = db_name or os.getenv("POSTGRES_DB", "postgres")
        user = cls._read_secret_or_env(user_secret_name, "POSTGRES_USER", "postgres")
        password = cls._read_secret_or_env(password_secret_name, "POSTGRES_PASSWORD", "postgres")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        return f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"

    @classmethod
    def create_test_url(
        cls,
        user_secret_name: str,
        password_secret_name: str,
    ) -> str:
        return cls.create_url(
            user_secret_name=user_secret_name,
            password_secret_name=password_secret_name,
            db_name="test_database",
        )

    def __init__(self, **kwargs):
        user_secret_name = os.getenv("PSQL_USER_SECRET_NAME", "")
        password_secret_name = os.getenv("PSQL_PASSWORD_SECRET_NAME", "")
        kwargs.setdefault(
            "url",
            type(self).create_url(
                user_secret_name=user_secret_name,
                password_secret_name=password_secret_name,
            ),
        )
        kwargs.setdefault(
            "test_url",
            type(self).create_test_url(
                user_secret_name=user_secret_name,
                password_secret_name=password_secret_name,
            ),
        )
        super().__init__(**kwargs)


class MiddlewareSettings(BaseModel):
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost", "http://localhost:3000"])
    allow_credentials: bool = True
    allow_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    allow_headers: list[str] = Field(
        default_factory=lambda: ["Authorization", "Content-Type", "X-Telegram-Init-Data"],
    )


class AuthSettings(BaseSettings):
    jwt_secret_key: str = Field(
        default="change-me-in-env",
        alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30,
        alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_minutes: int = Field(
        default=60 * 24 * 30,
        alias="JWT_REFRESH_TOKEN_EXPIRE_MINUTES",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class SmtpSettings(BaseModel):
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    from_email: str = ""


class WebSettings(BaseModel):
    jwt_secret: str = ""
    jwt_expiry_hours: int = 72
    cabinet_base_url: str = ""


class RedisSettings(BaseSettings):
    url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class PasswordResetSettings(BaseSettings):
    token_ttl_seconds: int = Field(default=1800, alias="PASSWORD_RESET_TOKEN_TTL_SECONDS")
    frontend_url: str = Field(default="https://site.ru/reset-password", alias="PASSWORD_RESET_FRONTEND_URL")
    rate_limit_by_login: int = Field(default=3, alias="PASSWORD_RESET_RATE_LIMIT_BY_LOGIN")
    rate_limit_by_ip: int = Field(default=10, alias="PASSWORD_RESET_RATE_LIMIT_BY_IP")
    rate_limit_window_seconds: int = Field(default=3600, alias="PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS")
    token_secret: str = Field(default="change-me-in-env", alias="PASSWORD_RESET_TOKEN_SECRET")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ChangePasswordSettings(BaseSettings):
    rate_limit_by_user: int = Field(default=5, alias="CHANGE_PASSWORD_RATE_LIMIT_BY_USER")
    rate_limit_by_ip: int = Field(default=10, alias="CHANGE_PASSWORD_RATE_LIMIT_BY_IP")
    rate_limit_window_seconds: int = Field(default=3600, alias="CHANGE_PASSWORD_RATE_LIMIT_WINDOW_SECONDS")
    failed_limit: int = Field(default=5, alias="CHANGE_PASSWORD_FAILED_LIMIT")
    failed_window_seconds: int = Field(default=900, alias="CHANGE_PASSWORD_FAILED_WINDOW_SECONDS")
    jwt_access_blacklist_enabled: bool = Field(default=False, alias="JWT_ACCESS_BLACKLIST_ENABLED")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AuthMeSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="AUTH_ME_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class UserMeSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="USER_ME_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class UserDeleteSettings(BaseSettings):
    require_password: bool = Field(default=True, alias="USER_DELETE_REQUIRE_PASSWORD")
    anonymize: bool = Field(default=False, alias="USER_DELETE_ANONYMIZE")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ProfileSummarySettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="PROFILE_SUMMARY_CACHE_TTL_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ProfileAddressesSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=120, alias="PROFILE_ADDRESSES_CACHE_TTL_SECONDS")
    user_addresses_limit: int = Field(default=20, alias="USER_ADDRESSES_LIMIT")
    address_delete_soft: bool = Field(default=True, alias="ADDRESS_DELETE_SOFT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.example", ".env"),
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="FASTAPI_CFG__",
        extra="ignore",
    )
    run: RunConfig = RunConfig()
    names: ProjectName = ProjectName()
    api: ApiPrefix = ApiPrefix()
    db: DbSettings = DbSettings()
    auth: AuthSettings = AuthSettings()
    middleware: MiddlewareSettings = MiddlewareSettings()
    smtp: SmtpSettings = SmtpSettings()
    web: WebSettings = WebSettings()
    redis: RedisSettings = RedisSettings()
    password_reset: PasswordResetSettings = PasswordResetSettings()
    change_password: ChangePasswordSettings = ChangePasswordSettings()
    auth_me: AuthMeSettings = AuthMeSettings()
    user_me: UserMeSettings = UserMeSettings()
    user_delete: UserDeleteSettings = UserDeleteSettings()
    profile_summary: ProfileSummarySettings = ProfileSummarySettings()
    profile_addresses: ProfileAddressesSettings = ProfileAddressesSettings()

    @property
    def tz(self) -> tzinfo:
        return ZoneInfo("Europe/Moscow")


settings = Settings()
