import React from 'react';
import Link from 'next/link';
import { cx, truncate, initials, stringToColor, budgetPercent, budgetBarColor, formatTokens, timeAgo } from '@/lib/utils';
import { StatusBadge } from '@/components/ui/Badge';
import type { Agent } from '@/lib/types';

interface AgentCardProps {
  agent: Agent;
}

const AgentCard: React.FC<AgentCardProps> = ({ agent }) => {
  const used = agent.token_usage_today ?? 0;
  const budget = agent.token_budget_today ?? 0;
  const pct = budgetPercent(used, budget);
  const barColor = budgetBarColor(pct);

  return (
    <Link href={`/agents/${agent.id}`}>
      <div className={cx(
        'rounded-xl border border-surface-border bg-surface-1 p-5',
        'flex flex-col gap-4 transition-all duration-150 cursor-pointer',
        'hover:border-surface-hover hover:shadow-elevated hover:-translate-y-0.5',
      )}>
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold text-white shrink-0"
              style={{ backgroundColor: stringToColor(agent.name) }}
            >
              {initials(agent.name)}
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-text-primary truncate">{agent.name}</p>
              <p className="text-xs text-text-muted truncate">{agent.role_name ?? 'No role assigned'}</p>
            </div>
          </div>
          <StatusBadge status={agent.status} animated />
        </div>

        {/* Current task */}
        <div className="rounded-lg bg-surface-3 px-3 py-2.5 min-h-[42px] flex items-center">
          <p className={cx(
            'text-xs leading-relaxed',
            agent.current_task_title ? 'text-text-secondary' : 'text-text-muted italic',
          )}>
            {agent.current_task_title
              ? truncate(agent.current_task_title, 80)
              : 'No active task'}
          </p>
        </div>

        {/* Token usage bar */}
        {budget > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-text-muted">Token usage today</span>
              <span className="text-xs text-text-secondary font-mono">
                {formatTokens(used)} / {formatTokens(budget)}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden">
              <div
                className={cx('h-full rounded-full transition-all duration-500', barColor)}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-1 border-t border-surface-border">
          <span className="text-xs text-text-muted">{agent.trigger_mode}</span>
          <span className="text-xs text-text-muted">{timeAgo(agent.last_active_at)}</span>
        </div>
      </div>
    </Link>
  );
};

export default AgentCard;
