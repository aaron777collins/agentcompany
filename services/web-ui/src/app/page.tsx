'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Header from '@/components/layout/Header';
import StatsCards from '@/components/dashboard/StatsCards';
import AgentStatusTable from '@/components/dashboard/AgentStatusTable';
import ActivityFeed from '@/components/dashboard/ActivityFeed';
import ApprovalQueue from '@/components/dashboard/ApprovalQueue';
import Button from '@/components/ui/Button';
import { SkeletonBlock } from '@/components/ui/Spinner';
import { metrics as metricsApi, approvals as approvalsApi } from '@/lib/api';
import { useAgents } from '@/hooks/useAgents';
import { useSSE } from '@/hooks/useSSE';
import { toast } from '@/hooks/useToast';
import type { PlatformMetrics, Approval } from '@/lib/types';

export default function DashboardPage() {
  const [platformMetrics, setPlatformMetrics] = useState<PlatformMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  const [approvalList, setApprovalList] = useState<Approval[]>([]);
  const [approvalsLoading, setApprovalsLoading] = useState(true);
  const [approvalsError, setApprovalsError] = useState<string | null>(null);

  const { agents, loading: agentsLoading, error: agentsError } = useAgents({ page_size: 10 });
  const { events, connected, error: sseError } = useSSE({ maxEvents: 50 });

  const fetchMetrics = useCallback(async () => {
    try {
      setMetricsError(null);
      const data = await metricsApi.platform();
      setPlatformMetrics(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load metrics';
      setMetricsError(msg);
      // Only toast on manual retries, not on background polling failures
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  const fetchApprovals = useCallback(async () => {
    try {
      setApprovalsError(null);
      const data = await approvalsApi.list({ status: 'pending' });
      setApprovalList(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load approvals';
      setApprovalsError(msg);
    } finally {
      setApprovalsLoading(false);
    }
  }, []);

  const handleRetryMetrics = useCallback(async () => {
    setMetricsLoading(true);
    try {
      const data = await metricsApi.platform();
      setPlatformMetrics(data);
      setMetricsError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load metrics';
      setMetricsError(msg);
      toast.error('Could not load metrics', msg);
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    fetchApprovals();
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
        {metricsError && !metricsLoading ? (
          <div className="rounded-xl border border-status-error/20 bg-status-error/5 px-5 py-4 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-status-error">Could not load metrics</p>
              <p className="text-xs text-text-muted mt-0.5">{metricsError}</p>
            </div>
            <Button variant="danger" size="sm" onClick={handleRetryMetrics}>
              Retry
            </Button>
          </div>
        ) : (
          <StatsCards metrics={platformMetrics} loading={metricsLoading} />
        )}

        {/* Middle row — agents table + activity feed */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            {agentsError && !agentsLoading ? (
              <AgentsErrorCard message={agentsError} />
            ) : (
              <AgentStatusTable agents={agents} loading={agentsLoading} />
            )}
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
        {approvalsError && !approvalsLoading ? (
          <div className="rounded-xl border border-status-error/20 bg-status-error/5 px-5 py-4 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-status-error">Could not load approvals</p>
              <p className="text-xs text-text-muted mt-0.5">{approvalsError}</p>
            </div>
            <Button variant="danger" size="sm" onClick={fetchApprovals}>
              Retry
            </Button>
          </div>
        ) : (
          <ApprovalQueue
            approvals={approvalList}
            loading={approvalsLoading}
            onRefresh={fetchApprovals}
          />
        )}
      </div>
    </div>
  );
}

function AgentsErrorCard({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-status-error/20 bg-status-error/5 p-8 flex flex-col items-center gap-3 text-center">
      <svg className="w-8 h-8 text-status-error" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
      <p className="text-sm text-status-error font-medium">Could not load agents</p>
      <p className="text-xs text-text-muted">{message}</p>
    </div>
  );
}
