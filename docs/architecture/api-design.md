# AgentCompany — API Design

**Version**: 1.0.0
**Date**: 2026-04-18
**Status**: Authoritative Design Document
**Base URL**: `https://{host}/api/v1`

---

## 1. API Design Principles

- **REST over HTTP/1.1+**. Resources are nouns, actions are HTTP methods. No RPC-style verb endpoints except where semantically necessary (e.g., `/start`, `/stop`).
- **JSON throughout**. All request and response bodies are `application/json`. No XML.
- **Versioned from day one**. The URL prefix `/api/v1/` is mandatory. Breaking changes increment the major version.
- **Consistent envelope**. All responses wrap data in a standard envelope with `data`, `meta`, and `error` fields.
- **Pagination on all list endpoints**. Cursor-based pagination for event streams; offset-based for resource lists.
- **Idempotency keys** on all mutating operations that trigger external tool actions.
- **OpenAPI 3.1 spec** is generated automatically from FastAPI decorators and is the source of truth.

---

## 2. Authentication

### 2.1 Scheme: Bearer JWT via Keycloak

All API requests (except `/api/v1/webhooks/*` and `/api/v1/health`) require:

```
Authorization: Bearer <jwt_token>
```

Tokens are issued by Keycloak via the standard OIDC Authorization Code flow (for humans) or Client Credentials flow (for agents/services).

### 2.2 Token Validation

The Core API validates tokens by:
1. Fetching the Keycloak JWKS endpoint at startup and caching public keys.
2. Verifying the JWT signature against the cached key set.
3. Checking `exp`, `iss`, and `aud` claims.
4. Extracting `sub` (user/agent ID), `realm_access.roles`, and the custom claim `org_id`.

**Token Claims Structure**:
```json
{
  "sub": "usr_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "iss": "https://auth.example.com/realms/agentcompany",
  "aud": ["agentcompany-api"],
  "exp": 1745107200,
  "iat": 1745103600,
  "org_id": "org_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "realm_access": {
    "roles": ["org:member", "company:admin"]
  },
  "resource_access": {
    "agentcompany-api": {
      "roles": ["task:create", "task:read", "agent:read"]
    }
  },
  "email": "human@example.com",
  "name": "Alice Smith",
  "agent": false
}
```

**Agent Token** (issued via Client Credentials):
```json
{
  "sub": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "iss": "https://auth.example.com/realms/agentcompany",
  "aud": ["agentcompany-api"],
  "exp": 1745190000,
  "org_id": "org_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "realm_access": {
    "roles": ["agent"]
  },
  "agent": true,
  "agent_id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX"
}
```

### 2.3 Webhook Authentication

Webhooks from Plane, Outline, and Mattermost use HMAC-SHA256 signature verification. Each tool is registered with a unique secret. The signature is in the `X-AgentCompany-Signature` header (or the tool's native header).

---

## 3. Standard Response Envelope

### 3.1 Success Response

```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "timestamp": "2026-04-18T12:00:00Z",
    "version": "1.0.0"
  }
}
```

### 3.2 List Response (Paginated)

```json
{
  "data": [ ... ],
  "meta": {
    "request_id": "req_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "timestamp": "2026-04-18T12:00:00Z",
    "pagination": {
      "total": 142,
      "limit": 20,
      "offset": 0,
      "next_offset": 20,
      "has_more": true
    }
  }
}
```

### 3.3 Error Response

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task with ID tsk_01HXK2J3M4N5P6Q7R8S9T0UVWX was not found.",
    "details": {},
    "request_id": "req_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "timestamp": "2026-04-18T12:00:00Z"
  }
}
```

### 3.4 HTTP Status Codes

| Code | Usage |
|---|---|
| 200 | Successful GET, PUT, PATCH |
| 201 | Successful POST (resource created) |
| 202 | Accepted — async operation started |
| 204 | Successful DELETE (no body) |
| 400 | Bad request — validation error |
| 401 | Missing or invalid authentication |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 409 | Conflict — duplicate or state violation |
| 422 | Unprocessable entity — semantic validation failed |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Service unavailable (circuit open) |

---

## 4. Rate Limiting

Rate limits are enforced at the Traefik layer and enforced again in Core API for defense-in-depth.

| Tier | Limit | Window | Scope |
|---|---|---|---|
| Anonymous | 10 req | 1 minute | Per IP |
| Human user | 500 req | 1 minute | Per user (sub claim) |
| Agent | 2000 req | 1 minute | Per agent |
| Admin | Unlimited | — | Per admin user |

Rate limit headers are returned on every response:
```
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 487
X-RateLimit-Reset: 1745103660
Retry-After: 47  (only on 429)
```

---

## 5. Pagination

### 5.1 Offset Pagination (resource lists)

Query parameters: `?limit=20&offset=0`

- `limit`: Maximum records per page. Default 20, maximum 100.
- `offset`: Zero-based record offset.

### 5.2 Cursor Pagination (event streams)

Query parameters: `?limit=50&cursor=evt_01HXK2J3M4N5P6Q7R8S9T0UVWX&direction=after`

- `cursor`: ID of the last event seen.
- `direction`: `after` (newer events) or `before` (older events).

---

## 6. Resource Endpoints

### 6.1 `/api/v1/companies`

**Resource**: A company is a virtual AI-powered organization. It contains agents, humans, roles, and projects.

#### GET /api/v1/companies

List all companies accessible to the authenticated user.

```
GET /api/v1/companies?limit=20&offset=0
Authorization: Bearer <jwt>
```

**Response 200**:
```json
{
  "data": [
    {
      "id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "name": "Acme AI Corp",
      "slug": "acme-ai-corp",
      "description": "An AI-powered marketing company",
      "org_id": "org_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "status": "active",
      "member_count": 12,
      "agent_count": 5,
      "created_at": "2026-04-01T09:00:00Z",
      "updated_at": "2026-04-18T08:30:00Z",
      "settings": {
        "timezone": "UTC",
        "default_language": "en",
        "human_approval_required": ["task:delete", "agent:configure"]
      }
    }
  ],
  "meta": {
    "request_id": "req_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "timestamp": "2026-04-18T12:00:00Z",
    "pagination": {
      "total": 3,
      "limit": 20,
      "offset": 0,
      "has_more": false
    }
  }
}
```

#### POST /api/v1/companies

Create a new company.

```
POST /api/v1/companies
Authorization: Bearer <jwt>
Content-Type: application/json
Idempotency-Key: idem_01HXK2J3M4N5P6Q7R8S9T0UVWX

{
  "name": "Acme AI Corp",
  "slug": "acme-ai-corp",
  "description": "An AI-powered marketing company",
  "settings": {
    "timezone": "UTC",
    "default_language": "en",
    "human_approval_required": ["task:delete", "agent:configure"]
  }
}
```

**Response 201**:
```json
{
  "data": {
    "id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "name": "Acme AI Corp",
    "slug": "acme-ai-corp",
    "status": "provisioning",
    "created_at": "2026-04-18T12:00:00Z"
  }
}
```

#### GET /api/v1/companies/{company_id}

```
GET /api/v1/companies/cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX
Authorization: Bearer <jwt>
```

**Response 200**: Full company object (same shape as list item).

#### PATCH /api/v1/companies/{company_id}

Partial update. Only provided fields are modified.

```
PATCH /api/v1/companies/cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "description": "Updated company description",
  "settings": {
    "timezone": "America/New_York"
  }
}
```

#### DELETE /api/v1/companies/{company_id}

Soft delete. Sets `status = "archived"`. Does not delete data.

```
DELETE /api/v1/companies/cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX
Authorization: Bearer <jwt>
```

**Response 204**: No body.

---

### 6.2 `/api/v1/agents`

**Resource**: An agent is an AI entity that belongs to a company, holds a role, and executes tasks.

#### GET /api/v1/agents

```
GET /api/v1/agents?company_id=cmp_01HX...&status=active&limit=20&offset=0
Authorization: Bearer <jwt>
```

**Query Parameters**:
- `company_id` (required): Filter by company
- `status`: `active` | `idle` | `paused` | `error`
- `role_id`: Filter by assigned role

**Response 200**:
```json
{
  "data": [
    {
      "id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "name": "Marketing Strategist",
      "slug": "marketing-strategist",
      "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "role_id": "rol_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "status": "active",
      "llm_config": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "temperature": 0.7,
        "max_tokens": 4096
      },
      "capabilities": ["task:execute", "doc:write", "search:read", "chat:post"],
      "system_prompt_ref": "spr_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "created_at": "2026-04-01T09:00:00Z",
      "last_active_at": "2026-04-18T11:45:00Z",
      "metrics": {
        "tasks_completed_24h": 14,
        "tokens_used_24h": 45000,
        "error_rate_24h": 0.02
      }
    }
  ]
}
```

#### POST /api/v1/agents

Create a new agent.

```json
{
  "name": "Marketing Strategist",
  "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "role_id": "rol_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "llm_config": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-5",
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "system_prompt": "You are a senior marketing strategist at Acme AI Corp...",
  "capabilities": ["task:execute", "doc:write", "search:read", "chat:post"],
  "tool_permissions": {
    "plane": ["issue:create", "issue:update", "issue:read"],
    "outline": ["document:create", "document:update", "document:read"],
    "mattermost": ["message:post", "channel:read"]
  }
}
```

**Response 201**: Created agent object.

#### POST /api/v1/agents/{agent_id}/start

```
POST /api/v1/agents/agt_01HX.../start
Authorization: Bearer <jwt>
```

**Response 202**:
```json
{
  "data": {
    "agent_id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "status": "starting",
    "message": "Agent is starting. Subscribe to /api/v1/events for status updates."
  }
}
```

#### POST /api/v1/agents/{agent_id}/stop

```
POST /api/v1/agents/agt_01HX.../stop
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "reason": "Scheduled maintenance",
  "drain": true
}
```

`drain: true` allows the agent to finish its current task before stopping.

**Response 202**: Same shape as `/start` response.

#### PATCH /api/v1/agents/{agent_id}

Update agent configuration. Changes take effect on the next task execution.

#### DELETE /api/v1/agents/{agent_id}

Soft delete. Agent must be in `idle` or `paused` status.

---

### 6.3 `/api/v1/roles`

**Resource**: A role defines capabilities, permissions, and the org chart position of an agent or human.

#### GET /api/v1/roles

```
GET /api/v1/roles?company_id=cmp_01HX...&limit=20&offset=0
Authorization: Bearer <jwt>
```

**Response 200**:
```json
{
  "data": [
    {
      "id": "rol_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "name": "Marketing Manager",
      "slug": "marketing-manager",
      "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "description": "Oversees all marketing operations",
      "level": 2,
      "reports_to_role_id": "rol_01HXK2J3M4N5P6Q7CEO",
      "permissions": [
        "task:create",
        "task:assign",
        "task:delete",
        "doc:create",
        "doc:publish",
        "agent:configure",
        "chat:post"
      ],
      "tool_access": {
        "plane": ["project:manage", "issue:all"],
        "outline": ["collection:manage", "document:all"],
        "mattermost": ["channel:manage", "message:all"]
      },
      "headcount": {
        "current": 1,
        "max": 3,
        "type": "agent"
      },
      "created_at": "2026-04-01T09:00:00Z"
    }
  ]
}
```

#### POST /api/v1/roles

Create a new role.

```json
{
  "name": "Marketing Manager",
  "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "description": "Oversees all marketing operations",
  "level": 2,
  "reports_to_role_id": "rol_01HXK2J3M4N5P6Q7CEO",
  "permissions": ["task:create", "task:assign", "doc:create"],
  "tool_access": {
    "plane": ["issue:create", "issue:read"],
    "outline": ["document:create", "document:read"]
  }
}
```

#### POST /api/v1/roles/{role_id}/assignments

Assign a user or agent to a role.

```json
{
  "assignee_id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "assignee_type": "agent",
  "effective_from": "2026-04-18T00:00:00Z",
  "effective_until": null
}
```

**Response 201**:
```json
{
  "data": {
    "assignment_id": "asgn_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "role_id": "rol_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "assignee_id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "assignee_type": "agent",
    "status": "active",
    "created_at": "2026-04-18T12:00:00Z"
  }
}
```

---

### 6.4 `/api/v1/tasks`

**Resource**: A task is a unit of work assigned to an agent or human. Tasks are mirrored to Plane issues.

#### GET /api/v1/tasks

```
GET /api/v1/tasks?company_id=cmp_01HX...&status=open&assigned_to=agt_01HX...&limit=20&offset=0
Authorization: Bearer <jwt>
```

**Query Parameters**:
- `company_id` (required)
- `status`: `open` | `in_progress` | `blocked` | `review` | `done` | `cancelled`
- `assigned_to`: User or agent ID
- `priority`: `urgent` | `high` | `medium` | `low`
- `due_before`: ISO 8601 datetime
- `created_after`: ISO 8601 datetime

**Response 200**:
```json
{
  "data": [
    {
      "id": "tsk_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "title": "Research top 5 competitors",
      "description": "Identify key competitors in the AI marketing space...",
      "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "status": "in_progress",
      "priority": "high",
      "assigned_to": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "assigned_type": "agent",
      "created_by": "usr_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "due_at": "2026-04-20T17:00:00Z",
      "external_refs": {
        "plane_issue_id": "PL-42",
        "plane_issue_url": "https://plane.example.com/acme/issues/PL-42"
      },
      "tags": ["research", "competitors", "q2-2026"],
      "parent_task_id": null,
      "subtask_ids": ["tsk_01HXK2J3M4N5P6Q7R8S9T0UVWX_sub1"],
      "created_at": "2026-04-18T10:00:00Z",
      "updated_at": "2026-04-18T11:30:00Z",
      "started_at": "2026-04-18T10:05:00Z",
      "completed_at": null
    }
  ]
}
```

#### POST /api/v1/tasks

Create a new task.

```json
{
  "title": "Research top 5 competitors",
  "description": "Identify key competitors in the AI marketing space and produce a briefing document.",
  "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "assigned_to": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "priority": "high",
  "due_at": "2026-04-20T17:00:00Z",
  "tags": ["research", "competitors"],
  "parent_task_id": null,
  "sync_to_plane": true,
  "metadata": {
    "expected_output": "Outline document with competitive analysis",
    "context_doc_ids": ["doc_01HXK2J3M4N5P6Q7R8S9T0UVWX"]
  }
}
```

**Response 201**: Created task object including `external_refs.plane_issue_id`.

#### PATCH /api/v1/tasks/{task_id}

Update task fields. Changes sync to Plane automatically.

#### POST /api/v1/tasks/{task_id}/comments

Add a comment to a task.

```json
{
  "body": "I've completed the initial research. See linked Outline document.",
  "author_id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "author_type": "agent"
}
```

#### GET /api/v1/tasks/{task_id}/timeline

Returns the full history of state changes, comments, and agent actions for a task.

**Response 200**:
```json
{
  "data": [
    {
      "id": "tl_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "task_id": "tsk_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "type": "status_change",
      "actor_id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "actor_type": "agent",
      "payload": {
        "from": "open",
        "to": "in_progress"
      },
      "timestamp": "2026-04-18T10:05:00Z"
    }
  ]
}
```

---

### 6.5 `/api/v1/search`

**Resource**: Unified search across all integrated tools and internal records.

#### GET /api/v1/search

```
GET /api/v1/search?q=competitor+analysis&scope=all&company_id=cmp_01HX...&limit=20&offset=0
Authorization: Bearer <jwt>
```

**Query Parameters**:
- `q` (required): Search query string
- `scope`: `all` | `tasks` | `documents` | `messages` | `agents` | `roles`
- `company_id` (required)
- `filters`: JSON-encoded filter object (e.g., `{"status": "active", "tags": ["q2"]}`)
- `sort`: `relevance` (default) | `created_at` | `updated_at`

**Response 200**:
```json
{
  "data": {
    "hits": [
      {
        "id": "doc_01HXK2J3M4N5P6Q7R8S9T0UVWX",
        "type": "document",
        "title": "Competitive Analysis Q2 2026",
        "excerpt": "...our top 5 competitors in the AI marketing space are...",
        "score": 0.97,
        "url": "https://docs.example.com/acme/competitive-analysis-q2",
        "created_at": "2026-04-15T09:00:00Z",
        "author": {
          "id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
          "name": "Marketing Strategist",
          "type": "agent"
        }
      },
      {
        "id": "tsk_01HXK2J3M4N5P6Q7R8S9T0UVWX",
        "type": "task",
        "title": "Research top 5 competitors",
        "excerpt": "Identify key competitors in the AI marketing space...",
        "score": 0.91,
        "status": "in_progress",
        "assigned_to": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX"
      }
    ],
    "total": 24,
    "facets": {
      "type": {
        "document": 12,
        "task": 8,
        "message": 4
      }
    },
    "query_time_ms": 18
  },
  "meta": {
    "request_id": "req_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "timestamp": "2026-04-18T12:00:00Z",
    "pagination": {
      "total": 24,
      "limit": 20,
      "offset": 0,
      "has_more": true
    }
  }
}
```

#### POST /api/v1/search/index

Force a re-index of a specific resource. Used after bulk imports.

```json
{
  "resource_type": "documents",
  "resource_ids": ["doc_01HX...", "doc_02HX..."],
  "company_id": "cmp_01HX..."
}
```

**Response 202**: Async indexing job accepted.

---

### 6.6 `/api/v1/events`

**Resource**: The event log and real-time event stream. Events are immutable records of things that happened.

#### GET /api/v1/events

```
GET /api/v1/events?company_id=cmp_01HX...&type=task.completed&limit=50&cursor=evt_01HX...&direction=after
Authorization: Bearer <jwt>
```

**Query Parameters**:
- `company_id` (required)
- `type`: Event type filter (e.g., `task.created`, `agent.error`, `tool.webhook`)
- `actor_id`: Filter by actor (user or agent)
- `resource_type`: `task` | `agent` | `document` | `message`
- `resource_id`: Filter by specific resource
- `cursor`: Cursor for pagination
- `direction`: `after` | `before`

**Response 200**:
```json
{
  "data": [
    {
      "id": "evt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "type": "task.completed",
      "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "actor": {
        "id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
        "type": "agent",
        "name": "Marketing Strategist"
      },
      "resource": {
        "type": "task",
        "id": "tsk_01HXK2J3M4N5P6Q7R8S9T0UVWX",
        "title": "Research top 5 competitors"
      },
      "payload": {
        "duration_seconds": 145,
        "tokens_used": 12400,
        "documents_created": 1,
        "outcome": "success"
      },
      "timestamp": "2026-04-18T11:45:00Z"
    }
  ],
  "meta": {
    "next_cursor": "evt_01HXK2J3M4N5P6Q7R8S9T0UVWX_next",
    "has_more": true
  }
}
```

#### GET /api/v1/events/stream

WebSocket endpoint for real-time event streaming.

```
GET /api/v1/events/stream?company_id=cmp_01HX...&types=task.*,agent.*
Upgrade: websocket
Authorization: Bearer <jwt>
```

Messages pushed over WebSocket follow the same event envelope. The client sends a `ping` frame every 30 seconds; the server echoes `pong`.

#### POST /api/v1/events/subscriptions

Register a webhook URL to receive event notifications.

```json
{
  "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "url": "https://your-service.example.com/webhook",
  "event_types": ["task.created", "task.completed", "agent.error"],
  "secret": "your_webhook_secret_here",
  "active": true
}
```

**Response 201**:
```json
{
  "data": {
    "subscription_id": "sub_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "url": "https://your-service.example.com/webhook",
    "event_types": ["task.created", "task.completed", "agent.error"],
    "status": "active",
    "created_at": "2026-04-18T12:00:00Z"
  }
}
```

---

### 6.7 `/api/v1/adapters`

**Resource**: Tool adapters connect AgentCompany to external tools. Each company can configure multiple adapters.

#### GET /api/v1/adapters

```
GET /api/v1/adapters?company_id=cmp_01HX...
Authorization: Bearer <jwt>
```

**Response 200**:
```json
{
  "data": [
    {
      "id": "adp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "tool": "plane",
      "version": "1.2.0",
      "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
      "status": "connected",
      "config": {
        "base_url": "https://plane.example.com",
        "workspace_slug": "acme-ai-corp",
        "project_id": "prj_01HXK2J3M4N5P6Q7R8S9T0UVWX",
        "api_key_ref": "secret://plane-api-key/acme"
      },
      "health": {
        "last_check": "2026-04-18T11:55:00Z",
        "status": "healthy",
        "latency_ms": 45
      },
      "capabilities": ["issue:create", "issue:read", "issue:update", "issue:delete", "webhook:receive"],
      "created_at": "2026-04-01T09:00:00Z"
    }
  ]
}
```

#### POST /api/v1/adapters

Register and configure a new adapter.

```json
{
  "tool": "plane",
  "company_id": "cmp_01HXK2J3M4N5P6Q7R8S9T0UVWX",
  "config": {
    "base_url": "https://plane.example.com",
    "workspace_slug": "acme-ai-corp",
    "project_id": "prj_01HXK2J3M4N5P6Q7R8S9T0UVWX",
    "api_key": "plane_api_key_here"
  }
}
```

Note: `api_key` is accepted in the request body but is immediately stored in the secrets manager. The returned adapter object contains `api_key_ref` (a secret reference), not the raw key.

#### POST /api/v1/adapters/{adapter_id}/test

Test the adapter connection.

**Response 200**:
```json
{
  "data": {
    "status": "healthy",
    "latency_ms": 38,
    "capabilities_verified": ["issue:create", "issue:read"],
    "tested_at": "2026-04-18T12:00:00Z"
  }
}
```

#### DELETE /api/v1/adapters/{adapter_id}

Disconnect and remove an adapter.

---

### 6.8 `/api/v1/metrics`

**Resource**: Token usage, cost tracking, and agent performance metrics.

#### GET /api/v1/metrics/usage

```
GET /api/v1/metrics/usage?company_id=cmp_01HX...&period=7d&granularity=day&agent_id=agt_01HX...
Authorization: Bearer <jwt>
```

**Query Parameters**:
- `company_id` (required)
- `period`: `1h` | `24h` | `7d` | `30d` | `custom`
- `start_at` / `end_at`: ISO 8601 (required when `period=custom`)
- `granularity`: `hour` | `day` | `week`
- `agent_id`: Filter by specific agent

**Response 200**:
```json
{
  "data": {
    "summary": {
      "total_tokens": 1250000,
      "prompt_tokens": 850000,
      "completion_tokens": 400000,
      "total_cost_usd": 18.75,
      "tasks_completed": 312,
      "tasks_failed": 8,
      "average_task_duration_seconds": 92,
      "period": "2026-04-11T00:00:00Z/2026-04-18T00:00:00Z"
    },
    "by_agent": [
      {
        "agent_id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
        "agent_name": "Marketing Strategist",
        "tokens": 450000,
        "cost_usd": 6.75,
        "tasks_completed": 112,
        "error_rate": 0.018
      }
    ],
    "timeseries": [
      {
        "timestamp": "2026-04-11T00:00:00Z",
        "tokens": 180000,
        "cost_usd": 2.70,
        "tasks": 44
      }
    ]
  }
}
```

#### GET /api/v1/metrics/performance

Agent performance and reliability metrics.

```
GET /api/v1/metrics/performance?company_id=cmp_01HX...&period=7d
Authorization: Bearer <jwt>
```

**Response 200**:
```json
{
  "data": {
    "agents": [
      {
        "agent_id": "agt_01HXK2J3M4N5P6Q7R8S9T0UVWX",
        "agent_name": "Marketing Strategist",
        "p50_task_duration_s": 68,
        "p99_task_duration_s": 240,
        "success_rate": 0.982,
        "retry_rate": 0.045,
        "tool_calls": {
          "plane": 312,
          "outline": 98,
          "mattermost": 445
        }
      }
    ]
  }
}
```

---

## 7. Webhook Ingestion

### 7.1 Endpoint

```
POST /api/v1/webhooks/{tool}/{secret_token}
```

Where `{tool}` is one of: `plane`, `outline`, `mattermost`.

The `{secret_token}` is a per-adapter, per-company token. It provides basic authentication without requiring a full JWT. The token is validated against the adapter record in Postgres.

### 7.2 Webhook Signature Verification

Each tool sends a signature header. The Core API verifies it before processing:

| Tool | Header | Algorithm |
|---|---|---|
| Plane | `X-Plane-Signature` | HMAC-SHA256 |
| Outline | `X-Outline-Signature` | HMAC-SHA256 |
| Mattermost | `X-Mattermost-Token` | Shared token (not HMAC) |

---

## 8. Idempotency

All `POST` endpoints that create resources or trigger external actions accept an optional `Idempotency-Key` header:

```
Idempotency-Key: idem_01HXK2J3M4N5P6Q7R8S9T0UVWX
```

- The key must be a string between 16 and 128 characters.
- The Core API caches the response for 24 hours keyed on `{user_id}:{idempotency_key}`.
- Duplicate requests with the same key return the cached response with status 200 and header `Idempotency-Replayed: true`.

---

## 9. API Versioning Strategy

- Current version: `v1`
- Breaking changes (field removal, type changes, endpoint removal) require a new version.
- Additive changes (new optional fields, new endpoints) do not require a version bump.
- Version `v1` is supported for a minimum of 24 months after `v2` is released.
- The `Sunset` response header announces deprecation: `Sunset: Sat, 18 Apr 2028 00:00:00 GMT`.
