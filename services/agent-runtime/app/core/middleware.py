"""Request logging and Prometheus metrics middleware.

RequestLoggingMiddleware wraps every inbound request to:
  1. Assign a short request_id for log correlation.
  2. Emit structured log lines at entry and exit that the StructuredFormatter
     in logging_config.py will serialize to JSON.
  3. Record HTTP request count and latency in Prometheus (no-op when
     prometheus_client is not installed).
  4. Attach X-Request-ID and X-Response-Time to every response so clients
     and load balancers can correlate timing without log access.

The middleware skips detailed metric recording for /health and /metrics so
those high-frequency probes do not inflate histogram bucket counts.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.monitoring import REQUEST_COUNT, REQUEST_LATENCY

logger = logging.getLogger(__name__)

# Endpoints that should not be recorded in Prometheus histograms.
# /health is called every 15 s by Docker and Traefik; /metrics is scraped by
# Prometheus itself.  Recording them adds noise without insight.
_SKIP_METRIC_PATHS = frozenset({"/health", "/metrics"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured logging + Prometheus instrumentation for every HTTP request.

    Attaches request_id to request.state so downstream handlers and log
    adapters can include it in their own log lines without extra plumbing.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        # 8-char prefix is long enough to be unique within a log window and
        # short enough to read in a terminal.
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        path = request.url.path
        method = request.method

        logger.info(
            "[%s] --> %s %s",
            request_id,
            method,
            path,
            extra={"request_id": request_id},
        )

        start_time = time.perf_counter()

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration = time.perf_counter() - start_time
            logger.error(
                "[%s] UNHANDLED %s %s (%.3fs): %s",
                request_id,
                method,
                path,
                duration,
                exc,
                exc_info=True,
                extra={"request_id": request_id},
            )
            raise

        duration = time.perf_counter() - start_time
        status_code = response.status_code

        logger.info(
            "[%s] <-- %s %s %d (%.3fs)",
            request_id,
            method,
            path,
            status_code,
            duration,
            extra={"request_id": request_id},
        )

        # Only record Prometheus observations for meaningful application paths.
        # High-frequency probe paths are excluded to avoid skewing p99 latency.
        if path not in _SKIP_METRIC_PATHS:
            REQUEST_COUNT.labels(
                method=method, endpoint=path, status=str(status_code)
            ).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=path).observe(duration)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response
