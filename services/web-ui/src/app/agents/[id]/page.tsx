'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Header from '@/components/layout/Header';
import AgentDetail from '@/components/agents/AgentDetail';
import { useAgent } from '@/hooks/useAgents';
import { agents as agentsApi } from '@/lib/api';
import { SkeletonBlock } from '@/components/ui/Spinner';
import Button from '@/components/ui/Button';
import type { AgentMemory } from '@/lib/types';

// ---------------------------------------------------------------------------
// Full-page skeleton that mirrors the AgentDetail layout
// ---------------------------------------------------------------------------

function AgentDetailSkeleton() {
  return (
    <div className="flex flex-col h-full">
      <div className="sticky top-0 z-20 flex items-center h-14 px-6 border-b border-surface-border bg-surface/80 backdrop-blur-md">
        <SkeletonBlock className="h-4 w-40" />
      </div>
      <div className="page-content space-y-6">
        {/* Agent header card */}
        <div className="rounded-xl border border-surface-border bg-surface-1 p-6">
          <div className="flex items-start gap-4">
            <SkeletonBlock className="w-14 h-14 rounded-2xl shrink-0" />
            <div className="flex-1 space-y-2">
              <SkeletonBlock className="h-5 w-48" />
              <SkeletonBlock className="h-3.5 w-32" />
              <div className="flex gap-2 pt-1">
                <SkeletonBlock className="h-6 w-20 rounded-full" />
                <SkeletonBlock className="h-6 w-20 rounded-full" />
              </div>
            </div>
          </div>
        </div>
        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-xl border border-surface-border bg-surface-1 p-4 space-y-2">
              <SkeletonBlock className="h-3 w-20" />
              <SkeletonBlock className="h-6 w-16" />
            </div>
          ))}
        </div>
        {/* Content area */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-3">
            <SkeletonBlock className="h-4 w-24" />
            {[...Array(5)].map((_, i) => (
              <SkeletonBlock key={i} className="h-10 rounded-lg" />
            ))}
          </div>
          <div className="space-y-3">
            <SkeletonBlock className="h-4 w-24" />
            {[...Array(4)].map((_, i) => (
              <SkeletonBlock key={i} className="h-12 rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

function AgentNotFoundCard({ id, message }: { id: string; message: string }) {
  const router = useRouter();

  return (
    <div className="flex flex-col h-full">
      <Header title="Agent Not Found" />
      <div className="page-content flex items-center justify-center pt-20">
        <div className="rounded-2xl border border-status-error/20 bg-status-error/5 p-10 text-center max-w-sm w-full space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-status-error/10 flex items-center justify-center mx-auto">
            <svg className="w-7 h-7 text-status-error" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2h-2" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-status-error">{message}</p>
            <p className="text-xs text-text-muted mt-1.5 font-mono break-all">{id}</p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => router.push('/agents')}>
            Back to Agents
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AgentDetailPage() {
  const params = useParams();
  const id = typeof params.id === 'string' ? params.id : params.id?.[0] ?? '';

  const { agent, loading, error, refetch } = useAgent(id);
  const [memories, setMemories] = useState<AgentMemory[]>([]);

  useEffect(() => {
    if (!id) return;
    agentsApi
      .memories(id)
      .then(setMemories)
      .catch(() => setMemories([]));
  }, [id]);

  if (loading) return <AgentDetailSkeleton />;

  if (error || !agent) {
    return (
      <AgentNotFoundCard
        id={id}
        message={error ?? 'Agent not found'}
      />
    );
  }

  return (
    <div className="flex flex-col h-full">
      <Header
        title={agent.name}
        subtitle={agent.role_name ?? undefined}
      />
      <div className="page-content">
        <AgentDetail agent={agent} memories={memories} onRefresh={refetch} />
      </div>
    </div>
  );
}
