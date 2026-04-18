'use client';

import React, { useState, useEffect } from 'react';
import { agents as agentsApi } from '@/lib/api';
import { formatTokens, formatCost } from '@/lib/utils';
import { SkeletonBlock } from '@/components/ui/Spinner';
import type { AgentTokenUsage, TokenUsagePoint } from '@/lib/types';

interface TokenUsageChartProps {
  agentId: string;
}

type Period = '24h' | '7d' | '30d';

/**
 * Bar chart rendered with pure CSS/SVG — no chart library needed.
 * Each bar is a proportionally-sized rectangle using SVG viewBox scaling.
 */
const BarChart: React.FC<{ points: TokenUsagePoint[] }> = ({ points }) => {
  if (points.length === 0) return null;

  const maxTokens = Math.max(...points.map((p) => p.total_tokens), 1);

  return (
    <div className="flex items-end gap-1 h-32">
      {points.map((point, i) => {
        const pct = (point.total_tokens / maxTokens) * 100;
        const date = new Date(point.timestamp);
        const label = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
            {/* Tooltip */}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1.5 rounded-lg bg-surface-4 border border-surface-border text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none">
              <p className="text-text-primary font-medium">{formatTokens(point.total_tokens)}</p>
              <p className="text-text-muted">{formatCost(point.cost_usd)}</p>
              <p className="text-text-disabled">{label}</p>
            </div>
            {/* Bar */}
            <div className="w-full flex items-end" style={{ height: '112px' }}>
              <div
                className="w-full rounded-t-sm bg-accent/70 hover:bg-accent transition-all duration-200"
                style={{ height: `${Math.max(pct, 2)}%` }}
              />
            </div>
            <span className="text-xs text-text-disabled truncate w-full text-center hidden md:block">
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
};

const TokenUsageChart: React.FC<TokenUsageChartProps> = ({ agentId }) => {
  const [period, setPeriod] = useState<Period>('7d');
  const [data, setData] = useState<AgentTokenUsage | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    agentsApi
      .tokenUsage(agentId, { period })
      .then((d) => { if (mounted) setData(d); })
      .catch(() => {})
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [agentId, period]);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-1 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-semibold text-text-primary">Token Usage</h3>
        <div className="flex items-center gap-1 bg-surface-3 rounded-lg p-0.5">
          {(['24h', '7d', '30d'] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
                period === p
                  ? 'bg-surface-1 text-text-primary shadow-sm'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="space-y-4">
          <div className="flex items-end gap-1 h-32">
            {[...Array(7)].map((_, i) => (
              <div key={i} className="flex-1">
                <SkeletonBlock
                  className="w-full rounded-t-sm"
                  style={{ height: `${Math.random() * 80 + 20}%` } as React.CSSProperties}
                />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="rounded-lg bg-surface-3 p-3">
                <SkeletonBlock className="h-3 w-16 mb-2" />
                <SkeletonBlock className="h-6 w-20" />
              </div>
            ))}
          </div>
        </div>
      ) : data ? (
        <>
          <BarChart points={data.points} />

          {/* Summary stats */}
          <div className="grid grid-cols-3 gap-3 mt-5">
            {[
              { label: 'Total Tokens', value: formatTokens(data.total_tokens) },
              { label: 'Input Tokens', value: formatTokens(data.total_input_tokens) },
              { label: 'Total Cost', value: formatCost(data.total_cost_usd) },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg bg-surface-3 p-3 text-center">
                <p className="text-xs text-text-muted">{label}</p>
                <p className="text-lg font-bold text-text-primary mt-1">{value}</p>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="text-center py-8 text-sm text-text-muted">
          No usage data available for this period.
        </div>
      )}
    </div>
  );
};

export default TokenUsageChart;
