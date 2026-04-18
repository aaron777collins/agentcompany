'use client';

import React, { useState } from 'react';
import { cx, formatDateTime, initials, stringToColor } from '@/lib/utils';
import { StatusBadge } from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import { agents as agentsApi } from '@/lib/api';
import AgentLogs from './AgentLogs';
import TokenUsageChart from './TokenUsageChart';
import type { Agent, AgentMemory } from '@/lib/types';

type Tab = 'overview' | 'logs' | 'tokens' | 'config' | 'memory';

interface AgentDetailProps {
  agent: Agent;
  memories: AgentMemory[];
  onRefresh: () => void;
}

const TAB_LABELS: Record<Tab, string> = {
  overview: 'Overview',
  logs: 'Logs',
  tokens: 'Token Usage',
  config: 'Configuration',
  memory: 'Memory',
};

const AgentDetail: React.FC<AgentDetailProps> = ({ agent, memories, onRefresh }) => {
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const handleAction = async (action: 'start' | 'stop' | 'trigger') => {
    setActionLoading(action);
    try {
      if (action === 'start') await agentsApi.start(agent.id);
      else if (action === 'stop') await agentsApi.stop(agent.id);
      else await agentsApi.trigger(agent.id);
      onRefresh();
    } catch {
      // Surface error through the parent's state management
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Agent header */}
      <div className="rounded-xl border border-surface-border bg-surface-1 p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-bold text-white shrink-0"
              style={{ backgroundColor: stringToColor(agent.name) }}
            >
              {initials(agent.name)}
            </div>
            <div>
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-xl font-bold text-text-primary">{agent.name}</h1>
                <StatusBadge status={agent.status} animated />
              </div>
              <p className="text-sm text-text-secondary mt-0.5">{agent.role_name ?? 'No role'}</p>
              <p className="text-xs text-text-muted mt-1">
                {agent.company_name ?? 'No company'} · {agent.trigger_mode} trigger
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {agent.status === 'stopped' || agent.status === 'error' ? (
              <Button
                variant="success"
                size="sm"
                loading={actionLoading === 'start'}
                onClick={() => handleAction('start')}
              >
                Start Agent
              </Button>
            ) : (
              <Button
                variant="danger"
                size="sm"
                loading={actionLoading === 'stop'}
                onClick={() => handleAction('stop')}
              >
                Stop Agent
              </Button>
            )}
            <Button
              variant="secondary"
              size="sm"
              loading={actionLoading === 'trigger'}
              onClick={() => handleAction('trigger')}
            >
              Trigger
            </Button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div>
        <div className="flex border-b border-surface-border -mb-px overflow-x-auto">
          {(Object.keys(TAB_LABELS) as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cx(
                'px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors',
                activeTab === tab
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted hover:text-text-primary hover:border-surface-hover',
              )}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
        </div>

        <div className="mt-6">
          {activeTab === 'overview' && <OverviewTab agent={agent} />}
          {activeTab === 'logs' && <AgentLogs agentId={agent.id} />}
          {activeTab === 'tokens' && <TokenUsageChart agentId={agent.id} />}
          {activeTab === 'config' && <ConfigTab agent={agent} />}
          {activeTab === 'memory' && <MemoryTab memories={memories} />}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Overview tab
// ---------------------------------------------------------------------------

const OverviewTab: React.FC<{ agent: Agent }> = ({ agent }) => (
  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div className="rounded-xl border border-surface-border bg-surface-1 p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4">Current Task</h3>
      {agent.current_task_title ? (
        <div className="rounded-lg bg-surface-3 px-4 py-3">
          <p className="text-sm text-text-secondary">{agent.current_task_title}</p>
          <p className="text-xs text-text-muted mt-1">{agent.current_task_id}</p>
        </div>
      ) : (
        <p className="text-sm text-text-muted italic">No active task</p>
      )}
    </div>

    <div className="rounded-xl border border-surface-border bg-surface-1 p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4">Details</h3>
      <dl className="space-y-2.5">
        {[
          ['Agent ID', agent.id],
          ['Company', agent.company_name ?? '—'],
          ['Role', agent.role_name ?? '—'],
          ['LLM Provider', agent.llm_config.provider],
          ['Model', agent.llm_config.model],
          ['Last Active', formatDateTime(agent.last_active_at)],
        ].map(([label, value]) => (
          <div key={label} className="flex items-start justify-between gap-4">
            <dt className="text-xs text-text-muted">{label}</dt>
            <dd className="text-xs font-mono text-text-secondary truncate max-w-[60%] text-right">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Config tab
// ---------------------------------------------------------------------------

const ConfigTab: React.FC<{ agent: Agent }> = ({ agent }) => {
  const { llm_config } = agent;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="rounded-xl border border-surface-border bg-surface-1 p-5">
        <h3 className="text-sm font-semibold text-text-primary mb-4">LLM Configuration</h3>
        <dl className="space-y-2.5">
          {[
            ['Provider', llm_config.provider],
            ['Model', llm_config.model],
            ['Temperature', llm_config.temperature.toString()],
            ['Max Tokens', llm_config.max_tokens.toLocaleString()],
            ['Monthly Budget', `$${llm_config.monthly_budget_usd}`],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between">
              <dt className="text-xs text-text-muted">{label}</dt>
              <dd className="text-xs font-mono text-text-secondary">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="rounded-xl border border-surface-border bg-surface-1 p-5">
        <h3 className="text-sm font-semibold text-text-primary mb-4">System Prompt</h3>
        {agent.system_prompt ? (
          <pre className="text-xs text-text-secondary whitespace-pre-wrap font-mono leading-relaxed bg-surface-3 rounded-lg p-3 max-h-64 overflow-y-auto">
            {agent.system_prompt}
          </pre>
        ) : (
          <p className="text-sm text-text-muted italic">Using default system prompt</p>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Memory tab
// ---------------------------------------------------------------------------

const MemoryTab: React.FC<{ memories: AgentMemory[] }> = ({ memories }) => {
  if (memories.length === 0) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-1 p-12 text-center">
        <p className="text-sm text-text-muted">No memories stored yet.</p>
        <p className="text-xs text-text-disabled mt-1">
          Memories are created as the agent completes tasks.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {memories.map((memory) => (
        <div
          key={memory.id}
          className="rounded-xl border border-surface-border bg-surface-1 p-4"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-accent">{memory.source}</span>
            <span className="text-xs text-text-muted">{formatDateTime(memory.created_at)}</span>
          </div>
          <p className="text-sm text-text-secondary leading-relaxed">{memory.content}</p>
        </div>
      ))}
    </div>
  );
};

export default AgentDetail;
