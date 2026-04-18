'use client';

import React, { useState, useEffect, useRef } from 'react';
import { agents as agentsApi } from '@/lib/api';
import { formatDateTime, cx } from '@/lib/utils';
import { SkeletonBlock } from '@/components/ui/Spinner';
import type { Event } from '@/lib/types';

interface AgentLogsProps {
  agentId: string;
}

const LOG_LEVEL_COLORS: Record<string, string> = {
  'agent.error': 'text-status-error',
  'agent.started': 'text-status-active',
  'agent.stopped': 'text-status-stopped',
  'task.completed': 'text-status-active',
  'token.budget_warning': 'text-status-idle',
};

const AgentLogs: React.FC<AgentLogsProps> = ({ agentId }) => {
  const [logs, setLogs] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    agentsApi
      .logs(agentId, { limit: 200 })
      .then((data) => { if (mounted) setLogs(data); })
      .catch(() => {})
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [agentId]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-1 overflow-hidden">
      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-surface-border flex items-center justify-between bg-surface-2">
        <span className="text-xs font-mono text-text-muted">
          {logs.length} events
        </span>
        <label className="flex items-center gap-2 text-xs text-text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="rounded"
          />
          Auto-scroll
        </label>
      </div>

      {/* Log output */}
      <div className="max-h-96 overflow-y-auto font-mono text-xs">
        {loading ? (
          <div className="p-5 space-y-2">
            {[...Array(8)].map((_, i) => (
              <SkeletonBlock key={i} className="h-3" style={{ width: `${60 + Math.random() * 40}%` } as React.CSSProperties} />
            ))}
          </div>
        ) : logs.length === 0 ? (
          <div className="p-8 text-center text-text-muted">No logs yet</div>
        ) : (
          <table className="w-full">
            <tbody>
              {logs.map((log, index) => (
                <tr
                  key={log.id}
                  className={cx(
                    'border-b border-surface-border/50 hover:bg-surface-3/40',
                    index % 2 === 0 ? '' : 'bg-surface-2/30',
                  )}
                >
                  <td className="px-4 py-2 text-text-disabled whitespace-nowrap w-40 align-top">
                    {formatDateTime(log.created_at)}
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap w-36 align-top">
                    <span className={cx(LOG_LEVEL_COLORS[log.type] ?? 'text-text-muted')}>
                      {log.type}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-text-secondary break-all">
                    {log.message}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};

export default AgentLogs;
