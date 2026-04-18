'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Header from '@/components/layout/Header';
import StatsCards from '@/components/dashboard/StatsCards';
import AgentStatusTable from '@/components/dashboard/AgentStatusTable';
import ActivityFeed from '@/components/dashboard/ActivityFeed';
import ApprovalQueue from '@/components/dashboard/ApprovalQueue';
import { metrics as metricsApi, approvals as approvalsApi } from '@/lib/api';
import { useAgents } from '@/hooks/useAgents';
import { useSSE } from '@/hooks/useSSE';
import type { PlatformMetrics, Approval } from '@/lib/types';

export default function DashboardPage() {
  const [platformMetrics, setPlatformMetrics] = useState<PlatformMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);

  const [approvalList, setApprovalList] = useState<Approval[]>([]);
  const [approvalsLoading, setApprovalsLoading] = useState(true);

  const { agents, loading: agentsLoading } = useAgents({ page_size: 10 });
  const { events, connected, error: sseError } = useSSE({ maxEvents: 50 });

  const fetchMetrics = useCallback(async () => {
    try {
      const data = await metricsApi.platform();
      setPlatformMetrics(data);
    } catch {
      // Platform metrics are non-critical — dashboard still usable without them
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  const fetchApprovals = useCallback(async () => {
    try {
      const data = await approvalsApi.list({ status: 'pending' });
      setApprovalList(data);
    } catch {
      // Non-fatal — queue shows "No pending approvals" if fetch fails
    } finally {
      setApprovalsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    fetchApprovals();
    // Refresh metrics every 30s — coarser than agent polling intentionally
    const metricsInterval = setInterval(fetchMetrics, 30_000);
    const approvalsInterval = setInterval(fetchApprovals, 15_000);
    return () => {
      clearInterval(metricsInterval);
      clearInterval(approvalsInterval);
    };
  }, [fetchMetrics, fetchApprovals]);

  return (
    <div className="flex flex-col h-full">
      <Header
        title="Dashboard"
        subtitle="AgentCompany overview"
      />

      <div className="flex-1 page-content space-y-6">
        {/* Stats row */}
        <StatsCards metrics={platformMetrics} loading={metricsLoading} />

        {/* Middle row — agents table + activity feed */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <AgentStatusTable agents={agents} loading={agentsLoading} />
          </div>
          <div>
            <ActivityFeed
              events={events}
              connected={connected}
              error={sseError}
            />
          </div>
        </div>

        {/* Approval queue */}
        <ApprovalQueue
          approvals={approvalList}
          loading={approvalsLoading}
          onRefresh={fetchApprovals}
        />
      </div>
    </div>
  );
}
