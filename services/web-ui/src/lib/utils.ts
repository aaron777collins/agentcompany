/**
 * Utility functions shared across the web-ui.
 * Keep these pure — no side effects, no imports from lib/api or React.
 */

import type { AgentStatus, TaskPriority, TaskStatus, ApprovalStatus } from './types';

// ---------------------------------------------------------------------------
// Date / time formatting
// ---------------------------------------------------------------------------

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

/**
 * Returns a human-friendly relative time string (e.g. "3 minutes ago").
 * Falls back to an absolute date string if the input is invalid.
 */
export function timeAgo(dateString: string | null | undefined): string {
  if (!dateString) return 'Never';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return 'Unknown';

  const diffMs = date.getTime() - Date.now();
  const diffSecs = Math.round(diffMs / 1000);
  const diffMins = Math.round(diffSecs / 60);
  const diffHours = Math.round(diffMins / 60);
  const diffDays = Math.round(diffHours / 24);

  if (Math.abs(diffSecs) < 60) return rtf.format(diffSecs, 'second');
  if (Math.abs(diffMins) < 60) return rtf.format(diffMins, 'minute');
  if (Math.abs(diffHours) < 24) return rtf.format(diffHours, 'hour');
  if (Math.abs(diffDays) < 30) return rtf.format(diffDays, 'day');
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Formats an ISO date string to a short human-readable form.
 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

// ---------------------------------------------------------------------------
// Number formatting
// ---------------------------------------------------------------------------

/**
 * Formats a token count with K/M suffix for compact display.
 */
export function formatTokens(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return count.toString();
}

/**
 * Formats a USD cost with 2-4 decimal places depending on magnitude.
 */
export function formatCost(usd: number): string {
  if (usd === 0) return '$0.00';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  if (usd < 1000) return `$${usd.toFixed(2)}`;
  return `$${Math.round(usd).toLocaleString()}`;
}

/**
 * Formats a percentage 0-100.
 */
export function formatPercent(value: number, decimals = 0): string {
  return `${value.toFixed(decimals)}%`;
}

// ---------------------------------------------------------------------------
// Status color mapping
// The tailwind class strings must be complete (not dynamic) so PurgeCSS keeps them.
// ---------------------------------------------------------------------------

export const agentStatusColors: Record<AgentStatus, { dot: string; badge: string; text: string }> = {
  active: {
    dot: 'bg-status-active',
    badge: 'bg-status-active/10 text-status-active border-status-active/20',
    text: 'text-status-active',
  },
  idle: {
    dot: 'bg-status-idle',
    badge: 'bg-status-idle/10 text-status-idle border-status-idle/20',
    text: 'text-status-idle',
  },
  error: {
    dot: 'bg-status-error',
    badge: 'bg-status-error/10 text-status-error border-status-error/20',
    text: 'text-status-error',
  },
  stopped: {
    dot: 'bg-status-stopped',
    badge: 'bg-status-stopped/10 text-status-stopped border-status-stopped/20',
    text: 'text-status-stopped',
  },
  pending: {
    dot: 'bg-status-pending',
    badge: 'bg-status-pending/10 text-status-pending border-status-pending/20',
    text: 'text-status-pending',
  },
};

export const taskStatusLabels: Record<TaskStatus, string> = {
  backlog: 'Backlog',
  todo: 'To Do',
  in_progress: 'In Progress',
  review: 'Review',
  done: 'Done',
};

export const taskPriorityColors: Record<TaskPriority, string> = {
  critical: 'text-red-500',
  high: 'text-orange-500',
  medium: 'text-yellow-500',
  low: 'text-slate-400',
};

export const taskPriorityIcons: Record<TaskPriority, string> = {
  critical: '!!',
  high: '!',
  medium: '~',
  low: '↓',
};

export const approvalStatusColors: Record<ApprovalStatus, string> = {
  pending: 'bg-status-pending/10 text-status-pending border-status-pending/20',
  approved: 'bg-status-active/10 text-status-active border-status-active/20',
  denied: 'bg-status-error/10 text-status-error border-status-error/20',
  expired: 'bg-status-stopped/10 text-status-stopped border-status-stopped/20',
};

// ---------------------------------------------------------------------------
// Class name helpers (avoids adding clsx as a dependency)
// ---------------------------------------------------------------------------

/**
 * Joins class name strings, filtering out falsy values.
 */
export function cx(...classes: (string | boolean | null | undefined)[]): string {
  return classes.filter((c): c is string => typeof c === 'string' && c.length > 0).join(' ');
}

// ---------------------------------------------------------------------------
// String utilities
// ---------------------------------------------------------------------------

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 1) + '…';
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

/**
 * Generates a deterministic color from a string (for avatar backgrounds).
 * Returns a Tailwind-compatible hsl string.
 */
export function stringToColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 60%, 50%)`;
}

// ---------------------------------------------------------------------------
// Budget bar calculation
// ---------------------------------------------------------------------------

export function budgetPercent(used: number, total: number): number {
  if (total === 0) return 0;
  return Math.min((used / total) * 100, 100);
}

/**
 * Returns a Tailwind color class for a budget bar based on how full it is.
 */
export function budgetBarColor(percent: number): string {
  if (percent >= 90) return 'bg-status-error';
  if (percent >= 70) return 'bg-status-idle';
  return 'bg-accent';
}

// ---------------------------------------------------------------------------
// Debounce
// ---------------------------------------------------------------------------

// Using any[] here is intentional — generic inference requires it for the return type to be callable
// with the original function's typed parameters via Parameters<T>
export function debounce<T extends (...args: Parameters<T>) => ReturnType<T>>(
  fn: T,
  delay: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout>;
  return (...args: Parameters<T>) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
