import redis.asyncio as aioredis
from fastapi import FastAPI
from dishka.integrations.fastapi import setup_dishka
from dishka import make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from source.tests.fake_ioc import TestProvider


def setup_test_app(
    app: FastAPI,
    test_session: AsyncSession,
    redis_client: aioredis.Redis,
) -> None:
    test_provider = TestProvider(test_session, redis_client)
    container = make_async_container(test_provider)
    setup_dishka(container=container, app=app)
