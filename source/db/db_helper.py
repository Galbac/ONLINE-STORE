from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from source.config.settings import settings


class DataBaseHelper:
    def __init__(
        self,
        url: str,
        echo: bool = False,
        echo_pool: bool = False,
        max_overflow: int = 10,
        pool_size: int = 5,
        use_null_pool: bool = False,
    ):
        engine_kwargs: dict[str, object] = {
            "url": url,
            "echo": echo,
            "echo_pool": echo_pool,
        }
        if use_null_pool:
            engine_kwargs["poolclass"] = NullPool
        else:
            engine_kwargs["max_overflow"] = max_overflow
            engine_kwargs["pool_size"] = pool_size

        self.engine: AsyncEngine = create_async_engine(**engine_kwargs)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def session_getter(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            yield session


db_helper = DataBaseHelper(
    url=str(settings.db.url),
    echo=settings.db.echo,
    echo_pool=settings.db.echo_pool,
    max_overflow=settings.db.max_overflow,
    pool_size=settings.db.pool_size,
)

test_db_helper = DataBaseHelper(
    url=str(settings.db.test_url),
    echo=settings.db.echo,
    echo_pool=settings.db.echo_pool,
    max_overflow=settings.db.max_overflow,
    pool_size=settings.db.pool_size,
    use_null_pool=True,
)
