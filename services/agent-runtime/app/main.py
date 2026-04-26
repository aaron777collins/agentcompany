"""FastAPI application entry point for the Agent Runtime service.

The lifespan context manager owns all startup and shutdown I/O:
  - PostgreSQL connection pool
  - Redis client
  - Event bus
  - APScheduler (for always_on and scheduled agent heartbeats)
  - HeartbeatService (routes ticks/events to agent trigger streams)
  - TriggerConsumer (reads from Redis Streams, dispatches to engine)

Horizontal scaling note: a single uvicorn worker is used (not multiple).
Concurrency is handled entirely by asyncio.  See agent-runtime.md § Deployment.

Startup order matters for dependency injection:
  1. DB, Redis, EventBus — infrastructure with no interdependencies
  2. AgentEngineService — needs event_bus; heartbeat set later
  3. APScheduler — must start before HeartbeatService registers jobs
  4. HeartbeatService — needs scheduler + redis + an agent_repo stub
  5. TriggerConsumer — needs redis + engine (HeartbeatService already running)
  6. Inject heartbeat_service back into engine_service
"""

import logging
import logging.config
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router, webhooks_router
from app.config import get_settings
from app.core.database import close_db, init_db
from app.core.events import init_event_bus
from app.engine.engine_service import AgentEngineService
from app.engine.heartbeat import HeartbeatService
from app.engine.trigger_consumer import TriggerConsumer

logger = logging.getLogger(__name__)


class _StubAgentRepo:
    """
    Minimal agent repository stub used by HeartbeatService.handle_platform_event.

    HeartbeatService.handle_platform_event() calls
    self._agents.list_active_event_triggered() to fan out events to agents.
    The API layer uses SQLAlchemy, but the HeartbeatService was designed for an
    asyncpg repo.  This stub satisfies the interface and delegates to the
    engine service (which has access to the session factory) to avoid bridging
    two ORM layers inside HeartbeatService.

    Phase 4 work: replace with a proper async repo that queries the DB.
    """

    async def list_active_event_triggered(self) -> list[dict[str, Any]]:
        # Return empty list — event routing for always_on/scheduled agents is
        # handled via the TriggerConsumer path.  Platform webhook events route
        # through engine_service.trigger_by_event() instead.
        return []


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

    # ── Agent engine (heartbeat injected below after scheduler is ready) ───────
    agent_manager = AgentEngineService(
        heartbeat_service=None,  # set below after scheduler starts
        event_bus=event_bus,
    )
    app.state.agent_manager = agent_manager
    logger.info("Agent engine service initialised")

    # ── APScheduler ────────────────────────────────────────────────────────────
    # timezone=utc keeps job fire times predictable across environments.
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("APScheduler started")

    # ── HeartbeatService ───────────────────────────────────────────────────────
    # The stub agent repo satisfies HeartbeatService's interface for platform
    # event routing.  Phase 4 will replace it with a real async repo.
    heartbeat = HeartbeatService(
        agent_repo=_StubAgentRepo(),
        trigger_queue=redis_client,
        scheduler=scheduler,
    )
    app.state.heartbeat_service = heartbeat
    # Inject back into engine so trigger_by_event can enqueue triggers
    agent_manager.set_heartbeat_service(heartbeat)
    logger.info("HeartbeatService initialised")

    # ── TriggerConsumer ────────────────────────────────────────────────────────
    trigger_consumer = TriggerConsumer(
        redis=redis_client,
        engine_service=agent_manager,
    )
    await trigger_consumer.start()
    app.state.trigger_consumer = trigger_consumer
    logger.info("TriggerConsumer started")

    yield

    # ── Shutdown (reverse order of startup) ───────────────────────────────────
    logger.info("Agent Runtime shutting down")

    await trigger_consumer.stop()
    logger.info("TriggerConsumer stopped")

    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")

    await agent_manager.shutdown()
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
