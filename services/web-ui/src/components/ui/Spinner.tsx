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
// Full-page skeleton — used while routes are loading initial data.
// Shows a shimmer skeleton rather than just a spinner for a more polished UX.
// ---------------------------------------------------------------------------

export const PageSkeleton: React.FC = () => (
  <div className="page-content space-y-6" aria-busy="true" aria-label="Loading content">
    {/* Top row */}
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="rounded-xl border border-surface-border bg-surface-1 p-5 space-y-3">
          <SkeletonBlock className="w-9 h-9 rounded-lg" />
          <SkeletonBlock className="h-3 w-20" />
          <SkeletonBlock className="h-7 w-16" />
        </div>
      ))}
    </div>
    {/* Content area */}
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 rounded-xl border border-surface-border bg-surface-1 p-5 space-y-3">
        <SkeletonBlock className="h-4 w-32" />
        {[...Array(5)].map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <SkeletonBlock className="w-8 h-8 rounded-full shrink-0" />
            <SkeletonBlock className="flex-1 h-4" />
            <SkeletonBlock className="w-16 h-6 rounded-full shrink-0" />
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-surface-border bg-surface-1 p-5 space-y-3">
        <SkeletonBlock className="h-4 w-24" />
        {[...Array(6)].map((_, i) => (
          <div key={i} className="flex items-center gap-2.5">
            <SkeletonBlock className="w-3 h-3 rounded-full shrink-0" />
            <SkeletonBlock className="flex-1 h-3" />
          </div>
        ))}
      </div>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// SkeletonBlock — placeholder for any piece of content while loading.
// Uses shimmer rather than plain pulse for a more refined look.
// ---------------------------------------------------------------------------

export const SkeletonBlock: React.FC<{
  className?: string;
  style?: React.CSSProperties;
}> = ({ className, style }) => (
  <div
    className={cx('rounded-md animate-shimmer', className)}
    style={style}
    aria-hidden="true"
  />
);

export default Spinner;
