import React from 'react';
import { cx, formatTokens, formatCost } from '@/lib/utils';
import { SkeletonBlock } from '@/components/ui/Spinner';
import type { PlatformMetrics } from '@/lib/types';

interface StatsCardsProps {
  metrics: PlatformMetrics | null;
  loading: boolean;
}

interface StatCardProps {
  title: string;
  value: string;
  subtext?: string;
  trend?: { value: string; positive: boolean };
  icon: React.ReactNode;
  accentColor?: string;
}

const StatCard: React.FC<StatCardProps> = ({ title, value, subtext, trend, icon, accentColor = 'text-accent' }) => (
  <div className="rounded-xl border border-surface-border bg-surface-1 p-5 flex flex-col gap-4">
    <div className="flex items-start justify-between">
      <div className={cx('p-2 rounded-lg bg-surface-3', accentColor)}>
        {icon}
      </div>
      {trend && (
        <span className={cx(
          'text-xs font-medium rounded-full px-2 py-0.5',
          trend.positive
            ? 'text-status-active bg-status-active/10'
            : 'text-status-error bg-status-error/10'
        )}>
          {trend.positive ? '↑' : '↓'} {trend.value}
        </span>
      )}
    </div>
    <div>
      <p className="text-xs text-text-muted font-medium uppercase tracking-wide">{title}</p>
      <p className="text-2xl font-bold text-text-primary mt-1">{value}</p>
      {subtext && <p className="text-xs text-text-secondary mt-1">{subtext}</p>}
    </div>
  </div>
);

const StatsCards: React.FC<StatsCardsProps> = ({ metrics, loading }) => {
  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="rounded-xl border border-surface-border bg-surface-1 p-5">
            <SkeletonBlock className="w-8 h-8 mb-4" />
            <SkeletonBlock className="w-16 h-3 mb-2" />
            <SkeletonBlock className="w-24 h-7" />
          </div>
        ))}
      </div>
    );
  }

  if (!metrics) return null;

  const cards: StatCardProps[] = [
    {
      title: 'Active Agents',
      value: `${metrics.active_agents}`,
      subtext: `${metrics.total_agents} total`,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2h-2" />
        </svg>
      ),
      accentColor: 'text-status-active',
    },
    {
      title: 'Total Tasks',
      value: `${metrics.total_tasks}`,
      subtext: `across ${metrics.total_companies} ${metrics.total_companies === 1 ? 'company' : 'companies'}`,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      accentColor: 'text-accent',
    },
    {
      title: 'Token Usage',
      value: formatTokens(metrics.total_token_usage),
      subtext: 'tokens across all agents',
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      accentColor: 'text-status-idle',
    },
    {
      title: 'Total Cost',
      value: formatCost(metrics.total_cost_usd),
      subtext: 'cumulative spend',
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      accentColor: 'text-status-pending',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <StatCard key={card.title} {...card} />
      ))}
    </div>
  );
};

export default StatsCards;
