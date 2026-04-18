'use client';

/**
 * useCompany / useCompanies — company data hooks.
 *
 * The active company is stored in localStorage so page refreshes and
 * navigation don't require re-selection. A future auth integration will
 * replace this with a value from the JWT.
 */

import { useState, useEffect, useCallback } from 'react';
import { companies as companiesApi } from '@/lib/api';
import type { Company } from '@/lib/types';

const ACTIVE_COMPANY_KEY = 'agentcompany.active_company_id';

// ---------------------------------------------------------------------------
// List hook
// ---------------------------------------------------------------------------

interface UseCompaniesResult {
  companies: Company[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useCompanies(): UseCompaniesResult {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    try {
      const res = await companiesApi.list({ page: 1, page_size: 50 });
      setCompanies(res.items);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load companies';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { companies, loading, error, refetch: fetch };
}

// ---------------------------------------------------------------------------
// Single company hook — also tracks the "active" selection globally
// ---------------------------------------------------------------------------

interface UseCompanyResult {
  company: Company | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useCompany(id: string): UseCompanyResult {
  const [company, setCompany] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!id) {
      setLoading(false);
      return;
    }
    try {
      const data = await companiesApi.get(id);
      setCompany(data);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load company';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    fetch();
  }, [fetch]);

  return { company, loading, error, refetch: fetch };
}

// ---------------------------------------------------------------------------
// Active company selection (persisted to localStorage)
// ---------------------------------------------------------------------------

export function getActiveCompanyId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ACTIVE_COMPANY_KEY);
}

export function setActiveCompanyId(id: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(ACTIVE_COMPANY_KEY, id);
}

export function useActiveCompany(): {
  activeCompanyId: string | null;
  setActiveCompanyId: (id: string) => void;
} {
  const [activeId, setActiveId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(ACTIVE_COMPANY_KEY);
  });

  const set = useCallback((id: string) => {
    localStorage.setItem(ACTIVE_COMPANY_KEY, id);
    setActiveId(id);
  }, []);

  return { activeCompanyId: activeId, setActiveCompanyId: set };
}
