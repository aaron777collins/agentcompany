'use client';

import React, { useState } from 'react';
import Header from '@/components/layout/Header';
import AgentCard from '@/components/agents/AgentCard';
import { useAgents } from '@/hooks/useAgents';
import { useCompanies } from '@/hooks/useCompany';
import Input from '@/components/ui/Input';
import Button from '@/components/ui/Button';
import { SkeletonBlock } from '@/components/ui/Spinner';
import type { AgentStatus } from '@/lib/types';

const STATUS_OPTIONS: { label: string; value: AgentStatus | '' }[] = [
  { label: 'All Statuses', value: '' },
  { label: 'Active', value: 'active' },
  { label: 'Idle', value: 'idle' },
  { label: 'Pending', value: 'pending' },
  { label: 'Error', value: 'error' },
  { label: 'Stopped', value: 'stopped' },
];

export default function AgentsPage() {
  const [statusFilter, setStatusFilter] = useState<AgentStatus | ''>('');
  const [companyFilter, setCompanyFilter] = useState('');
  const [search, setSearch] = useState('');

  const { agents, loading, total, error, refetch } = useAgents({
    status: statusFilter || undefined,
    company_id: companyFilter || undefined,
    page_size: 50,
  });

  const { companies } = useCompanies();

  // Client-side name search — API search not available for agents in MVP
  const filtered = search.trim()
    ? agents.filter(
        (a) =>
          a.name.toLowerCase().includes(search.toLowerCase()) ||
          (a.role_name ?? '').toLowerCase().includes(search.toLowerCase()),
      )
    : agents;

  const hasFilters = !!(statusFilter || companyFilter || search);

  return (
    <div className="flex flex-col h-full">
      <Header
        title="Agents"
        subtitle={loading ? undefined : `${total} total`}
      />

      <div className="page-content space-y-5">
        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="w-56">
            <Input
              placeholder="Search agents…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              icon={
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              }
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as AgentStatus | '')}
            className="h-9 px-3 text-sm rounded-lg border border-surface-border bg-surface-2 text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
          >
            {STATUS_OPTIONS.map(({ label, value }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>

          {companies.length > 0 && (
            <select
              value={companyFilter}
              onChange={(e) => setCompanyFilter(e.target.value)}
              className="h-9 px-3 text-sm rounded-lg border border-surface-border bg-surface-2 text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
            >
              <option value="">All Companies</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}

          {hasFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setStatusFilter(''); setCompanyFilter(''); setSearch(''); }}
            >
              Clear filters
            </Button>
          )}
        </div>

        {/* Error state */}
        {error && !loading && (
          <div className="rounded-xl border border-status-error/20 bg-status-error/5 px-5 py-4 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-status-error">Could not load agents</p>
              <p className="text-xs text-text-muted mt-0.5">{error}</p>
            </div>
            <Button variant="danger" size="sm" onClick={refetch}>
              Retry
            </Button>
          </div>
        )}

        {/* Skeleton grid */}
        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="rounded-xl border border-surface-border bg-surface-1 p-5 space-y-3">
                <div className="flex items-center gap-3">
                  <SkeletonBlock className="w-10 h-10 rounded-xl shrink-0" />
                  <div className="flex-1">
                    <SkeletonBlock className="h-3.5 w-28 mb-1.5" />
                    <SkeletonBlock className="h-3 w-20" />
                  </div>
                </div>
                <SkeletonBlock className="h-10 rounded-lg" />
                <SkeletonBlock className="h-2 rounded-full" />
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && filtered.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                  d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2h-2" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">
                {hasFilters ? 'No agents match your filters' : 'No agents yet'}
              </p>
              <p className="text-xs text-text-muted mt-1">
                {hasFilters
                  ? 'Try adjusting or clearing your filters'
                  : 'Create your first agent to get started'}
              </p>
            </div>
            {hasFilters && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setStatusFilter(''); setCompanyFilter(''); setSearch(''); }}
              >
                Clear filters
              </Button>
            )}
          </div>
        )}

        {/* Agent grid */}
        {!loading && !error && filtered.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
