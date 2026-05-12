from datetime import tzinfo
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

class DBSettings(BaseSettings):
    url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/grocery_store",
        alias="DATABASE_URL",
    )
    test_url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/grocery_store_test",
        alias="TEST_DATABASE_URL",
    )
    echo: bool = Field(default=False, alias="DB_ECHO")
    echo_pool: bool = Field(default=False, alias="DB_ECHO_POOL")
    max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    naming_convention: dict[str, str] = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


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
    db: DBSettings = DBSettings()
    auth: AuthSettings = AuthSettings()

    @property
    def tz(self) -> tzinfo:
        return ZoneInfo("Europe/Moscow")



settings = Settings()
