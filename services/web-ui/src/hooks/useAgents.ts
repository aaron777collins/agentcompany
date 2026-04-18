'use client';

/**
 * useAgents — fetches agent list with optional filters and polling.
 *
 * Uses manual polling rather than SWR/React Query to avoid adding
 * dependencies. Poll interval of 15s keeps the list fresh without
 * hammering the API.
 */

import { useState, useEffect, useCallback } from 'react';
import { agents as agentsApi } from '@/lib/api';
import type { Agent } from '@/lib/types';

interface UseAgentsOptions {
  company_id?: string;
  status?: string;
  role_id?: string;
  page?: number;
  page_size?: number;
  /** Set to false to disable polling (e.g. on agent detail pages that use SSE instead) */
  poll?: boolean;
}

interface UseAgentsResult {
  agents: Agent[];
  total: number;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

const POLL_INTERVAL_MS = 15_000;

export function useAgents(options: UseAgentsOptions = {}): UseAgentsResult {
  const { poll = true, ...params } = options;

  const [agents, setAgents] = useState<Agent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    try {
      const res = await agentsApi.list(params);
      setAgents(res.items);
      setTotal(res.total);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load agents';
      setError(msg);
    } finally {
      setLoading(false);
    }
    // Stringifying params to use as dep — avoids reference equality issues
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params)]);

  useEffect(() => {
    setLoading(true);
    fetch();
  }, [fetch]);

  // Polling — refreshes the list in the background to catch status changes
  useEffect(() => {
    if (!poll) return;
    const id = setInterval(fetch, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetch, poll]);

  return { agents, total, loading, error, refetch: fetch };
}

// ---------------------------------------------------------------------------
// Single agent hook — used on the detail page
// ---------------------------------------------------------------------------

interface UseAgentResult {
  agent: Agent | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useAgent(id: string): UseAgentResult {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!id) return;
    try {
      const data = await agentsApi.get(id);
      setAgent(data);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load agent';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    fetch();
  }, [fetch]);

  return { agent, loading, error, refetch: fetch };
}
