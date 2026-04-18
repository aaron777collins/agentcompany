import React from 'react';
import Link from 'next/link';
import { cx, timeAgo, truncate, initials, stringToColor } from '@/lib/utils';
import { StatusBadge } from '@/components/ui/Badge';
import { SkeletonBlock } from '@/components/ui/Spinner';
import type { Agent } from '@/lib/types';

interface AgentStatusTableProps {
  agents: Agent[];
  loading: boolean;
}

const Avatar: React.FC<{ name: string }> = ({ name }) => (
  <div
    className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
    style={{ backgroundColor: stringToColor(name) }}
  >
    {initials(name)}
  </div>
);

const AgentStatusTable: React.FC<AgentStatusTableProps> = ({ agents, loading }) => {
  if (loading) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-1 overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-border">
          <SkeletonBlock className="h-4 w-32" />
        </div>
        <div className="divide-y divide-surface-border">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center gap-4 px-5 py-3">
              <SkeletonBlock className="w-7 h-7 rounded-full" />
              <SkeletonBlock className="h-3 w-28 flex-1" />
              <SkeletonBlock className="h-5 w-16 rounded-full" />
              <SkeletonBlock className="h-3 w-40 hidden md:block" />
              <SkeletonBlock className="h-3 w-20 hidden lg:block" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-surface-border bg-surface-1 overflow-hidden">
      <div className="px-5 py-4 border-b border-surface-border flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">Agent Status</h3>
        <Link href="/agents" className="text-xs text-accent hover:text-accent-hover transition-colors">
          View all →
        </Link>
      </div>

      {agents.length === 0 ? (
        <div className="px-5 py-12 text-center text-sm text-text-muted">
          No agents configured yet.{' '}
          <Link href="/agents" className="text-accent hover:underline">Create one →</Link>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border">
                <th className="text-left px-5 py-2.5 text-xs font-medium text-text-muted uppercase tracking-wide">
                  Agent
                </th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-text-muted uppercase tracking-wide">
                  Status
                </th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-text-muted uppercase tracking-wide hidden md:table-cell">
                  Current Task
                </th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-text-muted uppercase tracking-wide hidden lg:table-cell">
                  Last Active
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {agents.map((agent) => (
                <tr
                  key={agent.id}
                  className="hover:bg-surface-3/50 transition-colors group"
                >
                  <td className="px-5 py-3">
                    <Link href={`/agents/${agent.id}`} className="flex items-center gap-3">
                      <Avatar name={agent.name} />
                      <div>
                        <p className="font-medium text-text-primary group-hover:text-accent transition-colors">
                          {agent.name}
                        </p>
                        <p className="text-xs text-text-muted">{agent.role_name ?? 'No role'}</p>
                      </div>
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={agent.status} animated />
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    <span
                      className={cx(
                        'text-xs',
                        agent.current_task_title ? 'text-text-secondary' : 'text-text-muted italic',
                      )}
                    >
                      {agent.current_task_title
                        ? truncate(agent.current_task_title, 48)
                        : 'No active task'}
                    </span>
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell text-xs text-text-muted">
                    {timeAgo(agent.last_active_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default AgentStatusTable;
