import React from 'react';
import { cx, agentStatusColors } from '@/lib/utils';
import type { AgentStatus } from '@/lib/types';

interface BadgeProps {
  label: string;
  className?: string;
}

interface StatusBadgeProps {
  status: AgentStatus;
  animated?: boolean;
}

/**
 * Generic badge — pass className to control color.
 */
export const Badge: React.FC<BadgeProps> = ({ label, className }) => (
  <span
    className={cx(
      'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium',
      className,
    )}
  >
    {label}
  </span>
);

/**
 * Agent status badge with a colored dot indicator.
 * The animated prop adds a ping animation for active agents.
 */
export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, animated = false }) => {
  const colors = agentStatusColors[status];

  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
        colors.badge,
      )}
    >
      <span className="relative flex h-1.5 w-1.5">
        {animated && status === 'active' && (
          <span
            className={cx(
              'absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping',
              colors.dot,
            )}
          />
        )}
        <span className={cx('relative inline-flex rounded-full h-1.5 w-1.5', colors.dot)} />
      </span>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
};

export default Badge;
