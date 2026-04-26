"""
Shared test fixtures for the agent-runtime test suite.

Architecture:
- All API tests go through a real FastAPI app (create_app()) with an
  in-memory SQLite database (aiosqlite) so the full middleware stack
  (auth dependency overrides, CORS, etc.) is exercised without Postgres.
- Auth is mocked by overriding the _get_token_claims dependency so tests
  never hit Keycloak.
- Redis is replaced with a fakeredis.aioredis.FakeRedis instance.
- External HTTP calls (Plane, Outline, Mattermost, Meilisearch) are
  mocked at the adapter/httpx level per test.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Environment variables — MUST be set before any app.* imports because
# app/main.py contains a module-level `app = create_app()` call that
# triggers get_settings() the moment the module is first imported.
# ---------------------------------------------------------------------------
_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_TEST_SECRET_KEY = "a" * 32
os.environ.setdefault("DATABASE_URL", _TEST_DB_URL)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", _TEST_SECRET_KEY)
os.environ.setdefault("WEBHOOK_SECRET_PLANE", "test-plane-secret")
os.environ.setdefault("WEBHOOK_SECRET_MATTERMOST", "test-mm-secret")
os.environ.setdefault("WEBHOOK_SECRET_OUTLINE", "test-outline-secret")

import fakeredis.aioredis as fake_aioredis
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import TokenClaims

# ---------------------------------------------------------------------------
# SQLite compatibility patches — must happen BEFORE any model imports
# ---------------------------------------------------------------------------
# 1. Replace PostgreSQL JSONB with SQLAlchemy's generic JSON so that SQLite
#    (used in tests) can compile the DDL without errors.
# 2. The metrics schema table (TokenUsage) must be excluded from SQLite
#    DDL because SQLite has no concept of schemas.

from sqlalchemy import JSON as _JSON
import sqlalchemy.dialects.postgresql as _pg_mod
_pg_mod.JSONB = _JSON  # type: ignore[assignment]
# Patch the symbols already imported into model modules
from sqlalchemy.dialects import postgresql as _pg_dialect
_pg_dialect.JSONB = _JSON  # type: ignore[assignment]

# Register all ORM models so SQLAlchemy can create the tables
# This import side-effect populates DeclarativeBase.metadata
from app.models import agent, approval, company, event, role, task  # noqa: F401
from app.models.base import Base  # noqa: F401
# Also import token_usage so the model is registered (but we skip its table in SQLite)
from app.models import token_usage  # noqa: F401


# ---------------------------------------------------------------------------
# Settings override — point app at SQLite for tests
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
TEST_SECRET_KEY = "a" * 32


def _make_test_settings():
    from app.config import Settings

    return Settings(
        database_url=TEST_DB_URL,
        redis_url="redis://localhost:6379/0",  # overridden in fixtures
        secret_key=TEST_SECRET_KEY,
        app_env="development",
        webhook_secret_plane="test-plane-secret",
        webhook_secret_mattermost="test-mm-secret",
        webhook_secret_outline="test-outline-secret",
    )


# ---------------------------------------------------------------------------
# In-process async DB engine — shared across all tests in a session
# ---------------------------------------------------------------------------

_test_engine = create_async_engine(TEST_DB_URL, echo=False)
_test_session_factory = async_sessionmaker(
    bind=_test_engine, expire_on_commit=False, autoflush=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    """
    Create ORM tables in the in-memory SQLite database once per test session.

    Tables that live in a named schema (e.g. metrics.token_usage) are skipped
    because SQLite does not support schemas.  The CostTracker's DB writes are
    mocked in test_cost_tracker.py so those tests do not require the table.
    """
    from app.models.base import Base as ModelBase

    def _create_non_schema_tables(conn):
        # Filter out tables that belong to a named schema — SQLite can't handle them.
        tables_without_schema = [
            t for t in ModelBase.metadata.sorted_tables
            if t.schema is None
        ]
        ModelBase.metadata.create_all(conn, tables=tables_without_schema)

    async with _test_engine.begin() as conn:
        await conn.run_sync(_create_non_schema_tables)

    yield

    def _drop_non_schema_tables(conn):
        tables_without_schema = [
            t for t in ModelBase.metadata.sorted_tables
            if t.schema is None
        ]
        ModelBase.metadata.drop_all(conn, tables=tables_without_schema)

    async with _test_engine.begin() as conn:
        await conn.run_sync(_drop_non_schema_tables)


# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_redis():
    """Return a fakeredis async client for the duration of one test."""
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.flushall()
    await redis.aclose()


# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession that wraps every test in a savepoint and rolls
    it back afterward so tests never leave rows in the DB.
    """
    async with _test_session_factory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


# ---------------------------------------------------------------------------
# JWT / auth helpers
# ---------------------------------------------------------------------------

def make_token_claims(
    sub: str = "user-test-001",
    org_id: str = "org-test-001",
    roles: list[str] | None = None,
    company_id: str | None = None,
    is_agent: bool = False,
) -> TokenClaims:
    return TokenClaims(
        sub=sub,
        org_id=org_id,
        is_agent=is_agent,
        agent_id=sub if is_agent else None,
        company_id=company_id,
        roles=roles if roles is not None else ["org:admin"],
        email="test@example.com",
        name="Test User",
    )


# Default admin claims used by most tests
DEFAULT_ADMIN_CLAIMS = make_token_claims(roles=["org:admin"])
DEFAULT_MEMBER_CLAIMS = make_token_claims(roles=["org:member"])


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return fake Bearer auth headers (token content is irrelevant; dep is overridden)."""
    return {"Authorization": "Bearer test-jwt-token"}


# ---------------------------------------------------------------------------
# FastAPI app with dependency overrides
# ---------------------------------------------------------------------------

def build_test_app(claims: TokenClaims | None = None) -> FastAPI:
    """
    Return a FastAPI app wired for testing:
      - SQLite in-memory DB via overridden get_db
      - Fake Redis on app.state
      - Mocked agent engine service on app.state
      - JWT dependency replaced with a fixed TokenClaims
    """
    import os
    from app.dependencies import _get_token_claims, get_db
    from app.engine.engine_service import AgentEngineService
    from app.main import create_app

    # Set minimum required environment variables so Settings validation passes.
    # We use os.environ because pydantic-settings reads from it at __init__ time.
    os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("SECRET_KEY", TEST_SECRET_KEY)
    os.environ.setdefault("WEBHOOK_SECRET_PLANE", "test-plane-secret")
    os.environ.setdefault("WEBHOOK_SECRET_MATTERMOST", "test-mm-secret")
    os.environ.setdefault("WEBHOOK_SECRET_OUTLINE", "test-outline-secret")

    # Clear lru_cache so settings are re-read with the test values
    import app.config as _config_module
    _config_module.get_settings.cache_clear()

    effective_claims = claims or DEFAULT_ADMIN_CLAIMS

    application = create_app()

    # Override auth — no parameters so FastAPI does not try to inject anything
    async def _fake_auth() -> TokenClaims:
        return effective_claims

    # Override DB — no parameters so FastAPI does not try to inject anything
    async def _fake_db():
        async with _test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[_get_token_claims] = _fake_auth
    application.dependency_overrides[get_db] = _fake_db

    # Wire fake Redis + mock engine onto app.state
    application.state.redis = fake_aioredis.FakeRedis(decode_responses=True)

    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(return_value=None)
    application.state.event_bus = mock_bus

    mock_engine = MagicMock(spec=AgentEngineService)
    mock_engine.start_agent = AsyncMock(return_value=None)
    mock_engine.stop_agent = AsyncMock(return_value=None)
    mock_engine.trigger_agent = AsyncMock(return_value="trigger-001")
    mock_engine.shutdown = AsyncMock(return_value=None)
    application.state.agent_manager = mock_engine

    return application


@pytest_asyncio.fixture
async def app() -> FastAPI:
    return build_test_app()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient that speaks directly to the FastAPI app (no network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def build_authed_client(claims: TokenClaims):
    """
    Return an (app, AsyncClient) pair wired with specific JWT claims.
    Use as an async context manager inside a test.
    """
    application = build_test_app(claims=claims)
    transport = ASGITransport(app=application)
    return AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# Pre-created data fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def sample_company(db_session: AsyncSession):
    """Insert a Company row and return the ORM object."""
    from app.models.company import Company

    company_obj = Company(
        org_id="org-test-001",
        name="Test Company",
        slug="test-company",
        description="A test company",
        settings={"timezone": "UTC"},
        status="active",
    )
    db_session.add(company_obj)
    await db_session.flush()
    await db_session.refresh(company_obj)
    return company_obj


@pytest_asyncio.fixture
async def sample_role(db_session: AsyncSession, sample_company):
    """Insert a Role row and return the ORM object."""
    from app.models.role import Role

    role_obj = Role(
        org_id="org-test-001",
        company_id=sample_company.id,
        name="Engineer",
        slug="engineer",
        description="Software engineer role",
        level=1,
        permissions=["task:read", "task:write"],
        tool_access={"plane": True},
        max_headcount=5,
        headcount_type="agent",
    )
    db_session.add(role_obj)
    await db_session.flush()
    await db_session.refresh(role_obj)
    return role_obj


@pytest_asyncio.fixture
async def sample_agent(db_session: AsyncSession, sample_company, sample_role):
    """Insert an Agent row and return the ORM object."""
    from app.models.agent import Agent

    agent_obj = Agent(
        org_id="org-test-001",
        company_id=sample_company.id,
        role_id=sample_role.id,
        name="Test Agent",
        slug="test-agent",
        llm_config={"provider": "anthropic", "model": "claude-sonnet-4-5"},
        capabilities=["task:read", "task:write"],
        tool_permissions={"plane": True},
        status="idle",
    )
    db_session.add(agent_obj)
    await db_session.flush()
    await db_session.refresh(agent_obj)
    return agent_obj


# ---------------------------------------------------------------------------
# HMAC helpers for webhook tests
# ---------------------------------------------------------------------------

def make_plane_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def make_outline_signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
