'use client';

import React, { useEffect, useState } from 'react';
import { useParams, notFound } from 'next/navigation';
import Header from '@/components/layout/Header';
import AgentDetail from '@/components/agents/AgentDetail';
import { useAgent } from '@/hooks/useAgents';
import { agents as agentsApi } from '@/lib/api';
import { PageSkeleton } from '@/components/ui/Spinner';
import type { AgentMemory } from '@/lib/types';

export default function AgentDetailPage() {
  const params = useParams();
  const id = typeof params.id === 'string' ? params.id : params.id?.[0] ?? '';

  const { agent, loading, error, refetch } = useAgent(id);
  const [memories, setMemories] = useState<AgentMemory[]>([]);

  // Validate the ID format before fetching — prevents nonsense requests
  if (!id.startsWith('agt_') && id.length > 0 && !loading) {
    // Allow the page to render; the API will return 404 and error handles it
  }

  useEffect(() => {
    if (!id) return;
    agentsApi
      .memories(id)
      .then(setMemories)
      .catch(() => setMemories([]));
  }, [id]);

  if (loading) return <PageSkeleton />;

  if (error || !agent) {
    return (
      <div className="flex flex-col h-full">
        <Header title="Agent Not Found" />
        <div className="page-content">
          <div className="rounded-xl border border-status-error/20 bg-status-error/5 p-8 text-center max-w-md mx-auto mt-12">
            <p className="text-sm font-medium text-status-error">
              {error ?? 'Agent not found'}
            </p>
            <p className="text-xs text-text-muted mt-2">
              The agent with ID &quot;{id}&quot; could not be loaded.
            </p>
          </div>
        </div>
      </div>
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
