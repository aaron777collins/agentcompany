'use client';

/**
 * Toast notification system.
 *
 * ToastProvider should wrap the entire app (in layout.tsx). Individual toasts
 * are fired via the `toast()` helper from useToast.ts — no prop drilling needed.
 *
 * Stacks appear in the bottom-right corner, newest on top.
 * Each toast auto-dismisses after `duration` ms (default 5 s).
 */

import React from 'react';
import { cx } from '@/lib/utils';
import { useToastState } from '@/hooks/useToast';
import type { Toast, ToastVariant } from '@/hooks/useToast';

// ---------------------------------------------------------------------------
// Variant config
// ---------------------------------------------------------------------------

const variantConfig: Record<
  ToastVariant,
  { containerClass: string; iconPath: string; iconColor: string }
> = {
  success: {
    containerClass: 'border-status-active/30 bg-surface-1',
    iconColor: 'text-status-active',
    iconPath:
      'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  error: {
    containerClass: 'border-status-error/30 bg-surface-1',
    iconColor: 'text-status-error',
    iconPath:
      'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  warning: {
    containerClass: 'border-status-idle/30 bg-surface-1',
    iconColor: 'text-status-idle',
    iconPath:
      'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  },
  info: {
    containerClass: 'border-accent/30 bg-surface-1',
    iconColor: 'text-accent',
    iconPath:
      'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  },
};

// ---------------------------------------------------------------------------
// Single toast item
// ---------------------------------------------------------------------------

interface ToastItemProps {
  toast: Toast;
  onDismiss: (id: string) => void;
}

const ToastItem: React.FC<ToastItemProps> = ({ toast, onDismiss }) => {
  const config = variantConfig[toast.variant];

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cx(
        'flex items-start gap-3 w-80 rounded-xl border shadow-elevated',
        'px-4 py-3.5 animate-slide-up',
        config.containerClass,
      )}
    >
      {/* Icon */}
      <svg
        className={cx('w-5 h-5 shrink-0 mt-0.5', config.iconColor)}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
        aria-hidden="true"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d={config.iconPath} />
      </svg>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-text-primary leading-tight">
          {toast.title}
        </p>
        {toast.message && (
          <p className="text-xs text-text-secondary mt-0.5 leading-relaxed">
            {toast.message}
          </p>
        )}
      </div>

      {/* Dismiss */}
      <button
        onClick={() => onDismiss(toast.id)}
        className="shrink-0 p-0.5 rounded text-text-muted hover:text-text-primary transition-colors"
        aria-label="Dismiss notification"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
};

// ---------------------------------------------------------------------------
// ToastProvider — mounts the stack and wires up the emitter
// ---------------------------------------------------------------------------

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { toasts, dismiss } = useToastState();

  return (
    <>
      {children}

      {/* Toast stack — fixed bottom-right, stacked vertically with gap */}
      <div
        className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 items-end"
        aria-label="Notifications"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </>
  );
};

export default ToastProvider;
