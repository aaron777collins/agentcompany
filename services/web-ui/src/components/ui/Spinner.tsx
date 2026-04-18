import React from 'react';
import { cx } from '@/lib/utils';

type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg';

interface SpinnerProps {
  size?: SpinnerSize;
  className?: string;
}

const sizeClasses: Record<SpinnerSize, string> = {
  xs: 'w-3 h-3',
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-7 h-7',
};

const Spinner: React.FC<SpinnerProps> = ({ size = 'md', className }) => (
  <svg
    className={cx('animate-spin text-accent', sizeClasses[size], className)}
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
    />
  </svg>
);

// ---------------------------------------------------------------------------
// Full-page loading skeleton — used while routes load initial data
// ---------------------------------------------------------------------------

export const PageSkeleton: React.FC = () => (
  <div className="flex items-center justify-center h-64 w-full">
    <div className="flex flex-col items-center gap-3">
      <Spinner size="lg" />
      <p className="text-sm text-text-muted animate-pulse">Loading…</p>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Skeleton block — use as placeholder for content while data loads
// ---------------------------------------------------------------------------

export const SkeletonBlock: React.FC<{ className?: string; style?: React.CSSProperties }> = ({ className, style }) => (
  <div className={cx('rounded-md bg-surface-3 animate-pulse', className)} style={style} />
);

export default Spinner;
