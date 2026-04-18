import React from 'react';
import { cx } from '@/lib/utils';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Adds hover state — useful for clickable cards */
  hoverable?: boolean;
  /** Remove all padding */
  noPadding?: boolean;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ hoverable = false, noPadding = false, className, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cx(
        'rounded-xl border border-surface-border bg-surface-1 shadow-card',
        noPadding ? '' : 'p-5',
        hoverable &&
          'cursor-pointer transition-all duration-150 hover:border-surface-hover hover:shadow-elevated hover:-translate-y-0.5',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  ),
);

Card.displayName = 'Card';

// ---------------------------------------------------------------------------
// Card sub-components for consistent layout
// ---------------------------------------------------------------------------

export const CardHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  className,
  children,
  ...props
}) => (
  <div
    className={cx('flex items-center justify-between mb-4', className)}
    {...props}
  >
    {children}
  </div>
);

export const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({
  className,
  children,
  ...props
}) => (
  <h3 className={cx('text-sm font-semibold text-text-primary', className)} {...props}>
    {children}
  </h3>
);

export default Card;
