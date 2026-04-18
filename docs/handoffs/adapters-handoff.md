# Tool Adapters — Implementation Handoff

**Date**: 2026-04-18
**Status**: Complete
**Author**: Staff Engineer (agent)

---

## What Was Built

The complete adapter layer at `services/agent-runtime/app/adapters/`:

| File | Purpose |
|------|---------|
| `types.py` | Shared types: `NormalizedEvent`, `HealthStatus`, `AdapterError`, enums |
| `base.py` | Abstract base class all adapters implement |
| `plane.py` | Plane project management adapter |
| `outline.py` | Outline documentation wiki adapter |
| `mattermost.py` | Mattermost team chat adapter |
| `meilisearch_adapter.py` | Meilisearch unified search adapter |
| `registry.py` | `AdapterRegistry` — process-level lifecycle manager |
| `__init__.py` | Public exports |

---

## Architecture

Each adapter follows this contract:

```
initialize(config) → health_check() loop → shutdown()
```

The `AdapterRegistry` is the only entry point callers need. It owns initialization, replacement, health-checking, and shutdown. Callers never construct adapters directly.

```python
registry = AdapterRegistry()
await registry.register("acme", "plane", {
    "config": {"base_url": "https://plane.example.com", "workspace_slug": "acme", "project_id": "proj-1"},
    "secrets": {"api_key": "...", "webhook_secret": "..."},
})
plane = registry.get("acme", "plane")
issues = await plane.list_issues("proj-1")
```

---

## Config Schema

Every adapter's `initialize(config)` expects:

```python
{
    "config": {
        # Non-secret adapter-specific settings
        "base_url": "https://...",
        "workspace_slug": "acme",   # Plane only
        "project_id": "proj-1",     # Plane only
        "team_id": "team-abc",      # Mattermost only
        "collection_id": "col-xyz", # Outline only (optional default)
    },
    "secrets": {
        # Resolved from secrets manager — never logged
        "api_key": "...",           # Plane, Outline
        "webhook_secret": "...",    # Plane, Outline
        "bot_token": "...",         # Mattermost
        "webhook_token": "...",     # Mattermost
        "master_key": "...",        # Meilisearch
        "search_key": "...",        # Meilisearch
    }
}
```

---

## Capabilities

Each adapter declares a `capabilities` list. The agent runtime calls `adapter.supports("issue:create")` or `adapter.require_capability("issue:create", "create_issue")` before dispatching any operation.

| Adapter | Key Capabilities |
|---------|-----------------|
| Plane | `issue:create/read/update/delete`, `issue:comment`, `cycle:read/create`, `label:read/create`, `project:read/create`, `webhook:receive` |
| Outline | `document:create/read/update/delete/search/export`, `collection:read/create`, `webhook:receive` |
| Mattermost | `message:post/read/update/delete/search`, `channel:read/create/join`, `user:read`, `file:upload`, `reaction:add`, `webhook:receive` |
| Meilisearch | `search:query`, `search:multi_index`, `document:index`, `document:delete_index` |

---

## Webhook Verification

| Adapter | Mechanism |
|---------|-----------|
| Plane | HMAC-SHA256, `X-Plane-Signature: sha256=<hex>` |
| Outline | HMAC-SHA256, `X-Outline-Signature: sha256=<hex>` |
| Mattermost | Shared token in request body `{"token": "..."}` |
| Meilisearch | No webhooks — `verify_webhook_signature` always returns False |

The webhook handler in Core API calls:
```python
valid = adapter.verify_webhook_signature(raw_body, headers, secret)
if not valid:
    return 401
event = await adapter.handle_webhook(json.loads(raw_body), headers)
```

---

## Normalized Events

All adapters produce `NormalizedEvent` from `handle_webhook()`. The event type mapping:

| Plane Event | Normalized |
|-------------|------------|
| `issue.created` | `task.created` |
| `issue.updated` | `task.updated` |
| `issue.deleted` | `task.deleted` |
| `issue_comment.created` | `task.commented` |
| `cycle.created` | `cycle.created` |

| Outline Event | Normalized |
|---------------|------------|
| `documents.create` | `document.created` |
| `documents.update` | `document.updated` |
| `documents.publish` | `document.published` |
| `documents.archive` | `document.archived` |
| `documents.delete` | `document.deleted` |

| Mattermost Event | Normalized |
|-----------------|------------|
| Outgoing webhook with `trigger_word` | `message.mentioned` |
| Outgoing webhook without `trigger_word` | `message.posted` |

Unknown event types are preserved with a tool-namespaced prefix (e.g. `plane.some.new.thing`).

---

## Error Handling

All adapters raise `AdapterError` instead of raw `httpx` exceptions. `AdapterError` carries:

- `code: AdapterErrorCode` — machine-readable error classification
- `retryable: bool` — True for 429/5xx; the runtime's retry loop uses this
- `retry_after_seconds: int | None` — from 429 `Retry-After` header
- `tool` and `operation` — for structured logging and circuit-breaker labeling

The runtime circuit breaker pattern:
```python
try:
    result = await plane.create_issue(...)
except AdapterError as err:
    if err.retryable:
        # exponential backoff / circuit breaker
    else:
        # surface to agent as tool error
```

---

## Meilisearch Tenant Isolation

The `search()` and `search_all()` methods enforce `company_id` filtering:

- `search()` — `company_id` is optional but strongly recommended
- `search_all()` — `company_id` is required; omitting it raises `AdapterError(VALIDATION_ERROR)`

Every indexed document must contain `id` and `company_id`. The `_validate_document()` check enforces this before any indexing call reaches the API.

The three indexes (`tickets`, `documents`, `messages`) are created and configured by `_ensure_indexes()` during `initialize()`. Filterable attributes: `company_id`, `org_id`, `source`, `status`, `author`.

---

## What Comes Next

### Connecting to the Tool Sandbox

The tool implementations in `app/adapters/tools/` (see `agent-tools.md`) use higher-level "client" objects. These need to be wired to the adapters in `app/adapters/`. The pattern from the architecture doc:

```python
plane_adapter = registry.get(company_id, "plane")
tool = ProjectManagementTool(plane_adapter)
```

The `ProjectManagementTool.execute()` calls `self._plane.issues.create(...)` etc. — those call sites need to be updated to match the adapter method signatures documented above.

### Live Config Reload

`registry.register()` gracefully replaces an existing adapter (shuts down the old one, starts the new one). To support live config reloads from the DB, add a background task that polls `adapter_configs` for changes and calls `registry.register()` when a config row is updated.

### Circuit Breaker

The architecture spec calls for a circuit breaker per adapter instance. A straightforward implementation wraps `registry.get()` in a circuit breaker class that tracks consecutive failures from `AdapterError(retryable=True)` and stops calling the adapter for a backoff window when the threshold is hit.

### Integration Tests

The adapters have been validated with unit tests (mocked HTTP). Integration tests against real tool instances (or docker-compose stubs) should be added to `services/agent-runtime/tests/adapters/`. Each test should:

1. Spin up a docker-compose stack (Plane, Outline, Mattermost, Meilisearch)
2. Run `registry.register()` with real credentials
3. Assert health check passes
4. Exercise one create + read + delete round trip per adapter

### Meilisearch Index Synchronization

Currently, documents are indexed individually via `index_document()` or in bulk via `index_documents_batch()`. A sync worker is needed that:

- On startup: bulk-syncs existing Plane issues, Outline documents, and Mattermost posts
- On events: indexes new/updated documents as `NormalizedEvent`s arrive on the Redis bus

---

## Known Limitations

- **Plane `get_issue()`** uses the default `project_id` from config. If the agent needs to fetch an issue from a different project, the adapter needs a `project_id` parameter added to `get_issue()`.
- **Mattermost file upload** calls `get_user("me")` inside `add_reaction()` on every call. This is a minor inefficiency. The bot user ID should be cached during `initialize()`.
- **Outline `export_document()`** assumes Meilisearch returns the export content in `data`. The Outline API may return it differently for HTML format — verify against the running instance before relying on this.
- **StrEnum** — the enums use Python 3.11+ `StrEnum`. The project targets Python 3.12 so this is correct, but if backport to 3.10 is ever needed, revert to `(str, Enum)`.
