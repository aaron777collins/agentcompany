"""Prometheus metrics for the AgentCompany runtime.

All metrics are defined at module load time.  When prometheus_client is not
installed (e.g. during unit tests or minimal deploys) every metric degrades to
a no-op stub so the rest of the codebase never needs an import guard.

Calling convention for context managers:
    async with track_llm_call("ollama", "gemma3") as timer:
        response = await llm.complete(prompt)
    # timer.labels() records the observation automatically on exit

The /metrics endpoint handler (metrics_endpoint) is registered by main.py on
the bare ASGI app so it bypasses auth middleware.  Prometheus scrape credentials
should be enforced at the network / reverse-proxy level instead.
"""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

# Graceful degradation: the app must boot without prometheus_client.
# All metric objects expose the same call interface as the real ones so
# instrumentation code never needs to branch on PROMETHEUS_AVAILABLE.
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    # ---------------------------------------------------------------------------
    # No-op stubs — same public API, do nothing.
    # ---------------------------------------------------------------------------
    class _NoOpMetric:
        """Base stub that swallows every call silently."""

        def labels(self, **_kwargs: Any) -> "_NoOpMetric":
            return self

        def inc(self, _amount: float = 1) -> None:
            pass

        def observe(self, _value: float) -> None:
            pass

        def set(self, _value: float) -> None:
            pass

        def time(self) -> "_NoOpTimer":
            return _NoOpTimer()

    class _NoOpTimer:
        def __enter__(self) -> "_NoOpTimer":
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        async def __aenter__(self) -> "_NoOpTimer":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

    def Counter(_name: str, _doc: str, _labels: list[str] | None = None) -> _NoOpMetric:  # type: ignore[misc]
        return _NoOpMetric()

    def Histogram(_name: str, _doc: str, _labels: list[str] | None = None) -> _NoOpMetric:  # type: ignore[misc]
        return _NoOpMetric()

    def Gauge(_name: str, _doc: str, _labels: list[str] | None = None) -> _NoOpMetric:  # type: ignore[misc]
        return _NoOpMetric()

    def Info(_name: str, _doc: str) -> _NoOpMetric:  # type: ignore[misc]
        return _NoOpMetric()

    def generate_latest() -> bytes:  # type: ignore[misc]
        return b"# prometheus_client not installed\n"


# ==============================================================================
# HTTP / API layer
# ==============================================================================

REQUEST_COUNT = Counter(
    "agentcompany_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "agentcompany_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)

# ==============================================================================
# Agent lifecycle
# ==============================================================================

ACTIVE_AGENTS = Gauge(
    "agentcompany_active_agents",
    "Number of currently active agents",
    ["company_id"],
)

AGENT_RUNS = Counter(
    "agentcompany_agent_runs_total",
    "Total agent decision-loop runs",
    ["agent_id", "role", "status"],  # status: success | error | timeout
)

# ==============================================================================
# LLM calls
# ==============================================================================

LLM_CALLS = Counter(
    "agentcompany_llm_calls_total",
    "Total LLM API calls",
    ["provider", "model"],
)

LLM_TOKENS = Counter(
    "agentcompany_llm_tokens_total",
    "Total LLM tokens consumed",
    ["provider", "direction"],  # direction: prompt | completion
)

LLM_COST = Counter(
    "agentcompany_llm_cost_usd_total",
    "Cumulative LLM cost in USD",
    ["provider"],
)

LLM_LATENCY = Histogram(
    "agentcompany_llm_call_duration_seconds",
    "End-to-end LLM call latency in seconds",
    ["provider", "model"],
)

# ==============================================================================
# Tool / adapter calls
# ==============================================================================

TOOL_CALLS = Counter(
    "agentcompany_tool_calls_total",
    "Total adapter method invocations",
    ["adapter", "method", "status"],  # status: success | error
)

TOOL_LATENCY = Histogram(
    "agentcompany_tool_call_duration_seconds",
    "Adapter method call latency in seconds",
    ["adapter", "method"],
)

ADAPTER_HEALTH = Gauge(
    "agentcompany_adapter_healthy",
    "Adapter health status (1=healthy, 0=unhealthy)",
    ["adapter"],
)

# ==============================================================================
# Events
# ==============================================================================

EVENT_COUNT = Counter(
    "agentcompany_events_total",
    "Total domain events processed",
    ["type", "source"],
)

# ==============================================================================
# Infrastructure
# ==============================================================================

DB_POOL_SIZE = Gauge(
    "agentcompany_db_pool_size",
    "Current SQLAlchemy connection pool size",
)

# ==============================================================================
# Context managers — convenience helpers for call-site instrumentation
# ==============================================================================


@asynccontextmanager
async def track_llm_call(
    provider: str, model: str
) -> AsyncGenerator[None, None]:
    """Record LLM call count and latency around an awaited LLM operation.

    Usage:
        async with track_llm_call("ollama", "gemma3"):
            result = await client.chat(...)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        LLM_CALLS.labels(provider=provider, model=model).inc()
        LLM_LATENCY.labels(provider=provider, model=model).observe(
            time.perf_counter() - start
        )


@asynccontextmanager
async def track_tool_call(
    adapter: str, method: str
) -> AsyncGenerator[None, None]:
    """Record adapter invocation count, latency, and success/error status.

    Usage:
        async with track_tool_call("mattermost", "post_message"):
            await adapter.post_message(...)
    """
    start = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        TOOL_CALLS.labels(adapter=adapter, method=method, status=status).inc()
        TOOL_LATENCY.labels(adapter=adapter, method=method).observe(
            time.perf_counter() - start
        )


# ==============================================================================
# /metrics HTTP handler
# ==============================================================================


async def metrics_endpoint() -> tuple[bytes, str]:
    """Return the Prometheus text exposition and its content-type header.

    Wire this into the FastAPI app in main.py:

        from fastapi.responses import Response
        from app.core.monitoring import metrics_endpoint

        @app.get("/metrics", include_in_schema=False)
        async def prometheus_metrics():
            body, content_type = await metrics_endpoint()
            return Response(content=body, media_type=content_type)

    The endpoint is intentionally left out of the OpenAPI schema.
    Access control should be handled at the network layer (Traefik IP allow-list
    or an internal-only Docker network) rather than with a Bearer token, because
    Prometheus does not send auth headers by default.
    """
    return generate_latest(), CONTENT_TYPE_LATEST
