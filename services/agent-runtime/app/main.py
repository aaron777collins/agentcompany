"""FastAPI application entry point for the Agent Runtime service.

The lifespan context manager owns all startup and shutdown I/O:
  - PostgreSQL connection pool
  - Redis client
  - Event bus
  - Alembic migrations (run head at startup)

Horizontal scaling note: a single uvicorn worker is used (not multiple).
Concurrency is handled entirely by asyncio.  See agent-runtime.md § Deployment.
"""

import logging
import logging.config
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router, webhooks_router
from app.config import get_settings
from app.core.database import close_db, init_db
from app.core.events import init_event_bus

logger = logging.getLogger(__name__)


def _configure_logging(log_level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "app.logging_config.StructuredFormatter",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                }
            },
            "root": {
                "level": log_level.upper(),
                "handlers": ["console"],
            },
        }
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    _configure_logging(settings.log_level)

    logger.info("Agent Runtime starting up (env=%s)", settings.app_env)

    # ── Database ───────────────────────────────────────────────────────────────
    await init_db()
    logger.info("Database connection pool initialised")

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_client = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=20,
    )
    app.state.redis = redis_client
    logger.info("Redis client initialised")

    # ── Event bus ──────────────────────────────────────────────────────────────
    event_bus = init_event_bus(redis_client)
    app.state.event_bus = event_bus
    logger.info("Event bus initialised")

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("Agent Runtime shutting down")
    await redis_client.aclose()
    await close_db()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AgentCompany Runtime",
        description=(
            "Core orchestration service for AgentCompany. "
            "Manages agent lifecycle, tasks, roles, and real-time events."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(api_router)
    app.include_router(webhooks_router)

    # ── Health check ───────────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health(request: Request) -> JSONResponse:
        """Liveness probe.  Returns 200 if the service is running."""
        redis_ok = False
        try:
            r: aioredis.Redis = request.app.state.redis
            await r.ping()
            redis_ok = True
        except Exception:
            pass

        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "redis": "ok" if redis_ok else "degraded",
            },
        )

    return app


app = create_app()
