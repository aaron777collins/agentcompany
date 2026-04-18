/**
 * API client for the AgentCompany Core API.
 *
 * All methods throw ApiError on non-2xx responses so callers can rely on
 * consistent error shape. We use native fetch (no axios) to avoid a
 * dependency and to keep the bundle lean.
 *
 * The client is intentionally not a class — tree-shaking removes unused
 * endpoint groups more effectively with named exports.
 */

import type {
  Agent,
  AgentMemory,
  AgentTokenUsage,
  Approval,
  Company,
  Event,
  IntegrationHealth,
  PaginatedResponse,
  PlatformMetrics,
  Role,
  SearchResponse,
  Task,
  ApiError,
} from './types';

// Resolved at build time for static assets; falls back to localhost for dev
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

class ApiClientError extends Error implements ApiError {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly detail: unknown = null,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;

  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      // JWT is stored in a cookie by the SSO integration; include credentials
      // so the browser sends it automatically. Change to Bearer header when
      // Keycloak integration is wired (tracked in issue #42).
      ...options.headers,
    },
    credentials: 'include',
  });

  if (!res.ok) {
    let errorBody: Record<string, unknown> = {};
    try {
      errorBody = await res.json();
    } catch {
      // Response body may not be JSON (e.g., proxy 502 as HTML)
    }
    throw new ApiClientError(
      res.status,
      (errorBody.code as string) ?? `HTTP_${res.status}`,
      (errorBody.message as string) ?? `Request failed with status ${res.status}`,
      errorBody.detail ?? null,
    );
  }

  // 204 No Content returns no body
  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

function buildQuery(params: Record<string, unknown>): string {
  const filtered = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  );
  if (filtered.length === 0) return '';
  return '?' + new URLSearchParams(filtered.map(([k, v]) => [k, String(v)])).toString();
}

// ---------------------------------------------------------------------------
// Companies
// ---------------------------------------------------------------------------

export const companies = {
  list(params?: { page?: number; page_size?: number }): Promise<PaginatedResponse<Company>> {
    return request(`/companies${buildQuery(params ?? {})}`);
  },

  get(id: string): Promise<Company> {
    return request(`/companies/${id}`);
  },

  create(body: { name: string; description?: string; industry?: string }): Promise<Company> {
    return request('/companies', { method: 'POST', body: JSON.stringify(body) });
  },

  update(id: string, body: Partial<Pick<Company, 'name' | 'description' | 'industry'>>): Promise<Company> {
    return request(`/companies/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  },

  delete(id: string): Promise<void> {
    return request(`/companies/${id}`, { method: 'DELETE' });
  },
};

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export const agents = {
  list(params?: {
    company_id?: string;
    status?: string;
    role_id?: string;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<Agent>> {
    return request(`/agents${buildQuery(params ?? {})}`);
  },

  get(id: string): Promise<Agent> {
    return request(`/agents/${id}`);
  },

  create(body: Omit<Agent, 'id' | 'created_at' | 'last_active_at' | 'current_task_id' | 'current_task_title'>): Promise<Agent> {
    return request('/agents', { method: 'POST', body: JSON.stringify(body) });
  },

  update(id: string, body: Partial<Agent>): Promise<Agent> {
    return request(`/agents/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  },

  delete(id: string): Promise<void> {
    return request(`/agents/${id}`, { method: 'DELETE' });
  },

  start(id: string): Promise<Agent> {
    return request(`/agents/${id}/start`, { method: 'POST' });
  },

  stop(id: string): Promise<Agent> {
    return request(`/agents/${id}/stop`, { method: 'POST' });
  },

  trigger(id: string, payload?: Record<string, unknown>): Promise<void> {
    return request(`/agents/${id}/trigger`, {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    });
  },

  memories(id: string): Promise<AgentMemory[]> {
    return request(`/agents/${id}/memories`);
  },

  tokenUsage(id: string, params?: { period?: '24h' | '7d' | '30d' }): Promise<AgentTokenUsage> {
    return request(`/agents/${id}/token-usage${buildQuery(params ?? {})}`);
  },

  logs(id: string, params?: { limit?: number; before?: string }): Promise<Event[]> {
    return request(`/agents/${id}/logs${buildQuery(params ?? {})}`);
  },
};

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

export const roles = {
  list(params?: { company_id?: string }): Promise<PaginatedResponse<Role>> {
    return request(`/roles${buildQuery(params ?? {})}`);
  },

  get(id: string): Promise<Role> {
    return request(`/roles/${id}`);
  },

  create(body: Omit<Role, 'id' | 'created_at' | 'level'>): Promise<Role> {
    return request('/roles', { method: 'POST', body: JSON.stringify(body) });
  },

  update(id: string, body: Partial<Role>): Promise<Role> {
    return request(`/roles/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  },

  delete(id: string): Promise<void> {
    return request(`/roles/${id}`, { method: 'DELETE' });
  },
};

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

export const tasks = {
  list(params?: {
    company_id?: string;
    status?: string;
    assignee_agent_id?: string;
    priority?: string;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<Task>> {
    return request(`/tasks${buildQuery(params ?? {})}`);
  },

  get(id: string): Promise<Task> {
    return request(`/tasks/${id}`);
  },

  create(body: {
    company_id: string;
    title: string;
    description?: string;
    status?: string;
    priority?: string;
  }): Promise<Task> {
    return request('/tasks', { method: 'POST', body: JSON.stringify(body) });
  },

  update(id: string, body: Partial<Task>): Promise<Task> {
    return request(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  },

  assign(id: string, agent_id: string): Promise<Task> {
    return request(`/tasks/${id}/assign`, {
      method: 'POST',
      body: JSON.stringify({ agent_id }),
    });
  },
};

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export const search = {
  query(params: {
    q: string;
    type?: 'all' | 'ticket' | 'document' | 'message';
    company_id?: string;
    limit?: number;
  }): Promise<SearchResponse> {
    return request(`/search${buildQuery(params)}`);
  },
};

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------

export const metrics = {
  platform(company_id?: string): Promise<PlatformMetrics> {
    return request(`/metrics/platform${buildQuery({ company_id })}`);
  },

  tokens(params?: { company_id?: string; period?: '24h' | '7d' | '30d' }): Promise<AgentTokenUsage[]> {
    return request(`/metrics/tokens${buildQuery(params ?? {})}`);
  },

  costs(params?: { company_id?: string; period?: '7d' | '30d' | '90d' }): Promise<Record<string, number>> {
    return request(`/metrics/costs${buildQuery(params ?? {})}`);
  },
};

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

export const approvals = {
  list(params?: { company_id?: string; status?: string }): Promise<Approval[]> {
    return request(`/approvals${buildQuery(params ?? {})}`);
  },

  approve(id: string): Promise<Approval> {
    return request(`/approvals/${id}/approve`, { method: 'POST' });
  },

  deny(id: string, reason?: string): Promise<Approval> {
    return request(`/approvals/${id}/deny`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },
};

// ---------------------------------------------------------------------------
// Events (SSE) — returns the raw EventSource URL so callers can manage lifecycle
// ---------------------------------------------------------------------------

export const events = {
  /**
   * Returns the URL for the SSE stream. Callers should create an EventSource
   * themselves so they control reconnect logic and cleanup (see useSSE hook).
   */
  streamUrl(params?: { company_id?: string }): string {
    return `${API_BASE}/events/stream${buildQuery(params ?? {})}`;
  },
};

// ---------------------------------------------------------------------------
// Integrations health
// ---------------------------------------------------------------------------

export const integrations = {
  health(): Promise<IntegrationHealth[]> {
    return request('/integrations/health');
  },
};

// ---------------------------------------------------------------------------
// Org chart (roles tree with agent assignments)
// ---------------------------------------------------------------------------

export const orgChart = {
  get(company_id: string): Promise<import('./types').OrgNode> {
    return request(`/companies/${company_id}/org-chart`);
  },
};

// ---------------------------------------------------------------------------
// Re-export error class so callers can instanceof check
// ---------------------------------------------------------------------------

export { ApiClientError };

// Named bundle for convenience — mirrors the spec's api.X.Y call pattern
export const api = {
  companies,
  agents,
  roles,
  tasks,
  search,
  metrics,
  approvals,
  events,
  integrations,
  orgChart,
};
