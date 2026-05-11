"""Pytest fixtures.

* Override DB to in-memory aiosqlite.
* Override Redis with fakeredis (async).
* Provide an httpx AsyncClient bound to the FastAPI app via ASGI
  transport (no real network).
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

# Required env so Settings doesn't fail importing before fixtures swap it
os.environ.setdefault("DB_PASSWORD", "test")

import fakeredis.aioredis  # noqa: E402
import pytest_asyncio  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from api import redis_store  # noqa: E402
from api.app import create_app  # noqa: E402
from api.db import Base, get_sessionmaker, reset_engine_for_tests  # noqa: E402


@pytest_asyncio.fixture
async def _db():
    reset_engine_for_tests("sqlite+aiosqlite:///:memory:")
    from api.db import get_engine  # late import — engine was just reset
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def _redis():
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_store.reset_redis_for_tests(fake)
    yield fake
    await fake.flushall()
    await fake.aclose()


@pytest_asyncio.fixture
async def client(_db, _redis) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with LifespanManager(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def session(_db):
    """Direct DB session for assertions in service-level tests."""
    sm = get_sessionmaker()
    async with sm() as s:
        yield s
