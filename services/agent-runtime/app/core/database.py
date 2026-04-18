"""SQLAlchemy 2.0 async engine and session factory.

A single engine is created at startup and shared across requests.  Sessions are
per-request, managed via the get_db() dependency in dependencies.py.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,   # recycle stale connections silently
        echo=settings.app_env == "development",
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        raise RuntimeError("Database engine has not been initialised. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        raise RuntimeError("Session factory has not been initialised. Call init_db() first.")
    return _session_factory


async def init_db() -> None:
    """Create the engine and session factory during application startup."""
    global _engine, _session_factory
    _engine = create_engine()
    _session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        autoflush=False,
    )


async def close_db() -> None:
    """Dispose the engine during application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession for use as a FastAPI dependency."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
