# Observability

This document covers the monitoring, logging, and alerting strategy for the AgentCompany runtime.

## Stack

| Layer | Tool | Purpose |
|---|---|---|
| Metrics exposition | `prometheus_client` (Python) | Instrumentation in `agent-runtime` |
| Metrics collection | Prometheus 2.51 | Scrape + TSDB storage |
| Dashboards | Grafana 10.4 | Visualization and alerting |
| Structured logging | `StructuredFormatter` (`logging_config.py`) | JSON logs for aggregators |
| Request tracing | `RequestLoggingMiddleware` (`core/middleware.py`) | Per-request correlation IDs |

---

## Metrics catalog

All metrics are defined in `services/agent-runtime/app/core/monitoring.py`.

### HTTP layer

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agentcompany_http_requests_total` | Counter | `method`, `endpoint`, `status` | Total HTTP requests completed |
| `agentcompany_http_request_duration_seconds` | Histogram | `method`, `endpoint` | Request latency |

`/health` and `/metrics` are excluded from these metrics to avoid skewing p99 with probe traffic.

### Agent lifecycle

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agentcompany_active_agents` | Gauge | `company_id` | Agents currently in `active` or `starting` state |
| `agentcompany_agent_runs_total` | Counter | `agent_id`, `role`, `status` | Decision-loop executions; `status` is `success`, `error`, or `timeout` |

### LLM calls

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agentcompany_llm_calls_total` | Counter | `provider`, `model` | Total LLM API calls |
| `agentcompany_llm_tokens_total` | Counter | `provider`, `direction` | Tokens consumed; `direction` is `prompt` or `completion` |
| `agentcompany_llm_cost_usd_total` | Counter | `provider` | Cumulative LLM cost in USD |
| `agentcompany_llm_call_duration_seconds` | Histogram | `provider`, `model` | End-to-end LLM call latency |

### Tool / adapter calls

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agentcompany_tool_calls_total` | Counter | `adapter`, `method`, `status` | Adapter invocations; `status` is `success` or `error` |
| `agentcompany_tool_call_duration_seconds` | Histogram | `adapter`, `method` | Adapter call latency |
| `agentcompany_adapter_healthy` | Gauge | `adapter` | `1` = healthy, `0` = unhealthy |

### Domain events

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agentcompany_events_total` | Counter | `type`, `source` | Domain events published to the event bus |

### Infrastructure

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agentcompany_db_pool_size` | Gauge | — | SQLAlchemy connection pool current size |

---

## Instrumentation patterns

### Track an LLM call

```python
from app.core.monitoring import track_llm_call, LLM_TOKENS, LLM_COST

async with track_llm_call("ollama", "gemma3"):
    response = await llm_client.chat(prompt)

# After the call, record token counts from the response:
LLM_TOKENS.labels(provider="ollama", direction="prompt").inc(response.prompt_tokens)
LLM_TOKENS.labels(provider="ollama", direction="completion").inc(response.completion_tokens)
LLM_COST.labels(provider="ollama").inc(response.cost_usd)
```

### Track an adapter call

```python
from app.core.monitoring import track_tool_call

async with track_tool_call("mattermost", "post_message"):
    await mattermost.post_message(channel_id, text)
```

The context manager automatically increments `agentcompany_tool_calls_total` with `status=error` if the block raises.

---

## Logging conventions

### Format

All log records are emitted as single-line JSON objects by `StructuredFormatter` in `app/logging_config.py`.  Example:

```json
{
  "timestamp": "2026-04-18T14:23:01Z",
  "level": "INFO",
  "logger": "app.core.middleware",
  "message": "[a3f1c2b4] --> GET /api/v1/agents",
  "service": "agent-runtime",
  "request_id": "a3f1c2b4"
}
```

### Request IDs

`RequestLoggingMiddleware` assigns an 8-character hex prefix (from `uuid4`) to each inbound request and stores it as `request.state.request_id`.  It also appears in every log line emitted by the middleware and is returned to the client in the `X-Request-ID` response header.

To propagate the request ID into your own log lines, use a `LoggerAdapter`:

```python
import logging

def get_logger_for_request(request) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(
        logging.getLogger(__name__),
        extra={"request_id": request.state.request_id},
    )
```

`StructuredFormatter` reads the `request_id` extra field and includes it in the JSON output automatically.

### Standard context fields

| Field | Set by | Description |
|---|---|---|
| `request_id` | `RequestLoggingMiddleware` | Per-request correlation token |
| `agent_id` | Engine layer `LoggerAdapter` | Agent being processed |
| `run_id` | Decision loop | Current run identifier |
| `company_id` | Engine layer | Tenant scoping |

---

## Health check endpoints

| Endpoint | Path | Auth |
|---|---|---|
| Liveness | `GET /health` | None |
| Prometheus metrics | `GET /metrics` | Network-level (no app auth) |

`/health` returns `200 OK` with a JSON body reporting the status of dependent services:

```json
{ "status": "ok", "redis": "ok" }
```

It returns `200` even when Redis is degraded so Docker/Traefik health checks do not restart a pod that can still serve non-streaming requests.  A separate Prometheus alert should fire when `redis` is `"degraded"` (see alerting section below).

---

## Dashboard setup

1. Add the required environment variable to your `.env` file:

   ```
   GRAFANA_ADMIN_PASSWORD=<strong-password>
   ```

2. Start the monitoring overlay:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
   ```

3. Open Grafana at `http://localhost/grafana/`.  The "AgentCompany Runtime" dashboard is pre-provisioned and will appear under Dashboards immediately.

4. Prometheus is available at `http://localhost/prometheus/` for ad-hoc PromQL queries.

Direct port access for local development (bypasses Traefik):

```bash
PROMETHEUS_PORT=9090 GRAFANA_PORT=3001 \
  docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

---

## Alerting recommendations

These alerts are recommendations for Grafana or external Alertmanager rules.  They are not pre-provisioned because threshold values depend on deployment scale.

### HTTP

| Alert | Expression | Threshold | Severity |
|---|---|---|---|
| High 5xx rate | `sum(rate(agentcompany_http_requests_total{status=~"5.."}[5m])) / sum(rate(agentcompany_http_requests_total[5m]))` | > 0.01 (1%) | warning |
| High p99 latency | `histogram_quantile(0.99, sum(rate(agentcompany_http_request_duration_seconds_bucket[5m])) by (le))` | > 2s | warning |

### LLM cost

| Alert | Expression | Threshold | Severity |
|---|---|---|---|
| Hourly cost spike | `sum(rate(agentcompany_llm_cost_usd_total[1h])) * 3600` | > $5 | warning |
| Daily cost burn | `sum(increase(agentcompany_llm_cost_usd_total[24h]))` | > $50 | critical |

### Adapters

| Alert | Expression | Threshold | Severity |
|---|---|---|---|
| Adapter unhealthy | `agentcompany_adapter_healthy` | == 0 | critical |
| High adapter error rate | `sum(rate(agentcompany_tool_calls_total{status="error"}[5m])) / sum(rate(agentcompany_tool_calls_total[5m]))` | > 0.05 (5%) | warning |

### Agents

| Alert | Expression | Threshold | Severity |
|---|---|---|---|
| Agent run error rate | `sum(rate(agentcompany_agent_runs_total{status="error"}[5m])) / sum(rate(agentcompany_agent_runs_total[5m]))` | > 0.10 (10%) | critical |
| Active agent count near limit | `sum(agentcompany_active_agents)` | > 45 (given default max_concurrent_agents=50) | warning |
