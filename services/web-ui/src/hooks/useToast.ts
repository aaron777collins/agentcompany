'use client';

/**
 * Toast context and hook.
 *
 * Kept as a simple module-level event emitter rather than React Context so
 * API call sites (which are not components) can trigger toasts without
 * needing access to a context value. The ToastProvider subscribes to the
 * emitter and translates events into React state.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type ToastVariant = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  variant: ToastVariant;
  title: string;
  message?: string;
  /** Duration in ms before auto-dismiss. 0 = persist until manually closed. */
  duration?: number;
}

type ToastInput = Omit<Toast, 'id'>;

// ---------------------------------------------------------------------------
// Module-level emitter — lets non-component code fire toasts
// ---------------------------------------------------------------------------

type Listener = (toast: Toast) => void;
type DismissListener = (id: string) => void;

const addListeners = new Set<Listener>();
const dismissListeners = new Set<DismissListener>();

let idCounter = 0;

function nextId(): string {
  idCounter += 1;
  return `toast_${idCounter}`;
}

/** Fire a toast from anywhere — components or plain API call sites. */
export function toast(input: ToastInput): string {
  const id = nextId();
  const t: Toast = { duration: 5000, ...input, id };
  addListeners.forEach((l) => l(t));
  return id;
}

export function dismissToast(id: string): void {
  dismissListeners.forEach((l) => l(id));
}

// Convenience helpers so callers don't need to pass variant each time
toast.success = (title: string, message?: string) =>
  toast({ variant: 'success', title, message });

toast.error = (title: string, message?: string) =>
  toast({ variant: 'error', title, message });

toast.warning = (title: string, message?: string) =>
  toast({ variant: 'warning', title, message });

toast.info = (title: string, message?: string) =>
  toast({ variant: 'info', title, message });

// ---------------------------------------------------------------------------
// Hook — used inside ToastProvider
// ---------------------------------------------------------------------------

export function useToastState() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const add = useCallback((t: Toast) => {
    setToasts((prev) => [...prev, t]);

    if (t.duration && t.duration > 0) {
      const timer = setTimeout(() => dismiss(t.id), t.duration);
      timers.current.set(t.id, timer);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  useEffect(() => {
    addListeners.add(add);
    dismissListeners.add(dismiss);
    return () => {
      addListeners.delete(add);
      dismissListeners.delete(dismiss);
    };
  }, [add, dismiss]);

  // Clean up all timers on unmount
  useEffect(() => {
    const currentTimers = timers.current;
    return () => {
      currentTimers.forEach((timer) => clearTimeout(timer));
    };
  }, []);

  return { toasts, dismiss };
}
