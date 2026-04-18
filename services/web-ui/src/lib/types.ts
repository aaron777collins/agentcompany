/**
 * TypeScript types matching the AgentCompany backend schemas.
 * All IDs use the {prefix}_{ulid} format defined in the architecture spec.
 * Keep this file in sync with the Core API's Pydantic models.
 */

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

export type AgentStatus = 'active' | 'idle' | 'error' | 'stopped' | 'pending';
export type TaskStatus = 'backlog' | 'todo' | 'in_progress' | 'review' | 'done' | 'cancelled';
export type TaskPriority = 'critical' | 'high' | 'medium' | 'low';
export type TriggerMode = 'event' | 'schedule' | 'manual';
export type LLMProvider = 'openai' | 'anthropic' | 'ollama';

// ---------------------------------------------------------------------------
// Organization & Company
// ---------------------------------------------------------------------------

export interface Org {
  id: string;           // org_{ulid}
  name: string;
  slug: string;
  created_at: string;
}

export interface Company {
  id: string;           // cmp_{ulid}
  org_id: string;
  name: string;
  description: string | null;
  industry: string | null;
  created_at: string;
  updated_at: string;
  agent_count: number;
  active_agent_count: number;
}

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

export interface Role {
  id: string;           // rol_{ulid}
  company_id: string;
  name: string;
  description: string | null;
  parent_role_id: string | null;
  level: number;        // hierarchy depth — 0 = CEO
  created_at: string;
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export interface LLMConfig {
  provider: LLMProvider;
  model: string;
  temperature: number;
  max_tokens: number;
  monthly_budget_usd: number;
}

export interface Agent {
  id: string;           // agt_{ulid}
  company_id: string;
  role_id: string;
  name: string;
  status: AgentStatus;
  trigger_mode: TriggerMode;
  llm_config: LLMConfig;
  system_prompt: string | null;
  current_task_id: string | null;
  current_task_title: string | null;
  last_active_at: string | null;
  created_at: string;
  // Denormalized for list views — populated by the API
  role_name?: string;
  company_name?: string;
  token_usage_today?: number;
  token_budget_today?: number;
}

export interface AgentMemory {
  id: string;
  agent_id: string;
  content: string;
  source: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

export interface TaskLabel {
  id: string;
  name: string;
  color: string;
}

export interface Task {
  id: string;           // tsk_{ulid}
  company_id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  assignee_agent_id: string | null;
  assignee_name: string | null;
  labels: TaskLabel[];
  plane_issue_id: string | null;
  created_at: string;
  updated_at: string;
  due_date: string | null;
}

// ---------------------------------------------------------------------------
// Events (SSE stream payload)
// ---------------------------------------------------------------------------

export type EventType =
  | 'agent.started'
  | 'agent.stopped'
  | 'agent.error'
  | 'agent.task_assigned'
  | 'task.created'
  | 'task.status_changed'
  | 'task.completed'
  | 'approval.requested'
  | 'approval.granted'
  | 'approval.denied'
  | 'token.budget_warning'
  | 'system.health_change';

export interface Event {
  id: string;           // evt_{ulid}
  type: EventType;
  company_id: string;
  actor_id: string | null;     // agent or user who triggered it
  actor_name: string | null;
  subject_id: string | null;   // entity the event is about
  subject_type: string | null;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

export type ApprovalStatus = 'pending' | 'approved' | 'denied' | 'expired';

export interface Approval {
  id: string;           // apr_{ulid}
  company_id: string;
  agent_id: string;
  agent_name: string;
  action_type: string;
  description: string;
  status: ApprovalStatus;
  requested_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Token Usage & Metrics
// ---------------------------------------------------------------------------

export interface TokenUsagePoint {
  timestamp: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface AgentTokenUsage {
  agent_id: string;
  agent_name: string;
  period_start: string;
  period_end: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  points: TokenUsagePoint[];
}

export interface PlatformMetrics {
  total_companies: number;
  total_agents: number;
  active_agents: number;
  total_tasks: number;
  total_token_usage: number;
  total_cost_usd: number;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export type SearchResultType = 'ticket' | 'document' | 'message' | 'agent' | 'task';

export interface SearchResult {
  id: string;
  type: SearchResultType;
  title: string;
  snippet: string;
  url: string | null;
  source: string;       // 'plane' | 'outline' | 'mattermost' | 'agentcompany'
  created_at: string;
  score: number;
}

export interface SearchResponse {
  query: string;
  total: number;
  results: SearchResult[];
  took_ms: number;
}

// ---------------------------------------------------------------------------
// Integration Health
// ---------------------------------------------------------------------------

export type IntegrationStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

export interface IntegrationHealth {
  name: string;
  display_name: string;
  status: IntegrationStatus;
  latency_ms: number | null;
  last_checked_at: string;
  error_message: string | null;
}

// ---------------------------------------------------------------------------
// API pagination wrapper
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

// ---------------------------------------------------------------------------
// API error shape
// ---------------------------------------------------------------------------

export interface ApiError {
  status: number;
  code: string;
  message: string;
  detail: unknown;
}

// ---------------------------------------------------------------------------
// Org chart node (derived from roles + agents for rendering)
// ---------------------------------------------------------------------------

export interface OrgNode {
  id: string;
  name: string;
  role: string;
  type: 'human' | 'agent';
  status: AgentStatus | 'human';
  children: OrgNode[];
  agent_id: string | null;
}
