"""Async SQLAlchemy engine + session factory."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from api.config import get_settings


class Base(DeclarativeBase):
    """Single declarative base for all ORM models."""


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Yields a session and closes it after."""
    async with get_sessionmaker()() as session:
        yield session


def reset_engine_for_tests(database_url: str) -> None:
    """Replace the engine + sessionmaker for tests (in-memory sqlite)."""
    global _engine, _sessionmaker
    _engine = create_async_engine(database_url, pool_pre_ping=True)
    _sessionmaker = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession,
    )
