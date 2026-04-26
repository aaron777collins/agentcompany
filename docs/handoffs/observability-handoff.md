# Observability handoff

## What was built

Monitoring and observability infrastructure for the AgentCompany agent-runtime service.  All changes are additive — no existing files were modified.

## New files

### Runtime instrumentation

- `services/agent-runtime/app/core/monitoring.py`
  Prometheus metrics registry with no-op stubs so the service boots without `prometheus_client` installed.  Exports `track_llm_call` and `track_tool_call` async context managers for call-site instrumentation, and a `metrics_endpoint()` handler function ready to be wired into `main.py`.

- `services/agent-runtime/app/core/middleware.py`
  `RequestLoggingMiddleware` (Starlette `BaseHTTPMiddleware` subclass).  Assigns a short `request_id` to every request, emits structured log lines at ingress and egress, records Prometheus request count and latency, and injects `X-Request-ID` / `X-Response-Time` response headers.

### Prometheus configuration

- `configs/prometheus/prometheus.yml`
  Scrapes `agent-runtime:8000/metrics` every 15 seconds.  Also self-scrapes Prometheus.

### Grafana configuration

- `configs/grafana/provisioning/datasources.yml`
  Auto-provisions Prometheus as the default datasource.  UID `prometheus-agentcompany` is referenced in the dashboard JSON.

- `configs/grafana/provisioning/dashboards.yml`
  Tells Grafana to load dashboard JSON files from `/etc/grafana/dashboards` at startup.

- `configs/grafana/dashboards/agentcompany.json`
  Pre-built dashboard with panels for: request rate + latency, HTTP error rate, active agent count, agent run rate by role, LLM token rate, LLM cost rate (USD/hr), LLM call latency, tool call success/error rate, and adapter health status.

### Docker Compose overlay

- `docker-compose.monitoring.yml`
  Adds Prometheus and Grafana as optional services.  Usage:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
  ```
  Requires `GRAFANA_ADMIN_PASSWORD` in `.env`.

### Documentation

- `docs/architecture/observability.md`
  Full metrics catalog, logging conventions, call-site instrumentation examples, health check endpoint reference, dashboard setup guide, and alerting recommendations with PromQL expressions.

---

## What still needs to be done

### Wire middleware into main.py

`RequestLoggingMiddleware` is not registered yet.  Add it to `create_app()` in `main.py`:

```python
from app.core.middleware import RequestLoggingMiddleware

app.add_middleware(RequestLoggingMiddleware)
```

Middleware is applied in reverse declaration order in Starlette, so add it after `CORSMiddleware`.

### Expose /metrics endpoint in main.py

```python
from fastapi.responses import Response
from app.core.monitoring import metrics_endpoint

@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    body, content_type = await metrics_endpoint()
    return Response(content=body, media_type=content_type)
```

This should be added inside `create_app()` alongside the existing `/health` route.

### Add prometheus_client to requirements.txt

```
prometheus-client>=0.20
```

The monitoring module falls back silently to no-ops without it, but metrics will not be exported.

### Call track_llm_call / track_tool_call at call sites

The context managers in `monitoring.py` need to be wired into:

- The Ollama LLM adapter (wherever `httpx` calls are made to `/api/chat`)
- Each adapter method in `services/agent-runtime/app/adapters/` (Mattermost, Plane, Outline, Meilisearch)
- The decision loop in the agent engine wherever `AGENT_RUNS` and `ACTIVE_AGENTS` should be recorded

### Record token counts from LLM responses

After each LLM call, increment `LLM_TOKENS` and `LLM_COST` with the values returned in the response body.  The `track_llm_call` context manager only records call count and latency — token and cost counters must be incremented explicitly.

### Set ACTIVE_AGENTS gauge from engine state

`agentcompany_active_agents` is a Gauge that should be set whenever an agent transitions to/from active state.  The logical place is `AgentEngineService.start_agent` and `AgentEngineService.stop_agent` in `engine_service.py`.

### Add GRAFANA_ADMIN_PASSWORD to .env.example

The `docker-compose.monitoring.yml` requires `GRAFANA_ADMIN_PASSWORD`.  Add it to the project's `.env.example` (or equivalent reference file) so new developers know to set it.

---

## Decisions made

- **No-op stubs instead of conditional imports** — metrics code is scattered across many call sites.  Requiring every site to check `PROMETHEUS_AVAILABLE` would be noisy and error-prone.  The stub objects satisfy the same interface so instrumented code is always valid Python regardless of whether `prometheus_client` is installed.

- **Middleware excludes /health and /metrics** — both endpoints are called at high frequency by infrastructure (Docker health checks scrape every 15 s, Prometheus every 15 s).  Recording them inflates histogram bucket counts and masks real application latency percentiles.

- **/metrics has no application-level auth** — Prometheus does not send Bearer tokens by default.  Access control should be enforced at the network layer (internal Docker network, Traefik IP allow-list, or mTLS) rather than adding a custom Prometheus HTTP SD config.

- **Dashboard is read-only (`allowUiUpdates: false`)** — UI edits disappear on container restart.  Intentional changes should go through the JSON file in version control.
