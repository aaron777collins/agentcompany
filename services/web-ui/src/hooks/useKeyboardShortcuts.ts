'use client';

/**
 * useKeyboardShortcuts — global keyboard shortcut handler.
 *
 * Two-key sequences like "G then D" are handled with a 1.5 s window between
 * the prefix key and the action key. This matches the pattern used in apps
 * like GitHub and Linear.
 *
 * All handlers are registered on `document` with `capture: false` so they run
 * after any focused-element handlers, preventing accidental navigation when a
 * user is typing in an input.
 */

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';

export interface ShortcutDefinition {
  /** Human-readable label shown in the help modal */
  label: string;
  /** Key chord — either a single key or a two-key sequence like ['g', 'd'] */
  keys: string | [string, string];
  /** Whether to fire even when an input/textarea is focused */
  allowInInput?: boolean;
}

// Published shortcut definitions — imported by KeyboardShortcuts modal for display
export const SHORTCUTS: ShortcutDefinition[] = [
  { keys: 'k', label: 'Open command palette', allowInInput: false },
  { keys: '/', label: 'Keyboard shortcuts help', allowInInput: false },
  { keys: ['g', 'd'], label: 'Go to Dashboard' },
  { keys: ['g', 'a'], label: 'Go to Agents' },
  { keys: ['g', 't'], label: 'Go to Tasks' },
  { keys: ['g', 's'], label: 'Go to Settings' },
  { keys: 'Escape', label: 'Close modal / palette', allowInInput: true },
];

interface UseKeyboardShortcutsOptions {
  onOpenCommandPalette: () => void;
  onOpenShortcutsHelp: () => void;
}

const SEQUENCE_TIMEOUT_MS = 1500;

function isEditableTarget(el: EventTarget | null): boolean {
  if (!el || !(el instanceof HTMLElement)) return false;
  const tag = el.tagName.toLowerCase();
  return (
    tag === 'input' ||
    tag === 'textarea' ||
    tag === 'select' ||
    el.isContentEditable
  );
}

export function useKeyboardShortcuts({
  onOpenCommandPalette,
  onOpenShortcutsHelp,
}: UseKeyboardShortcutsOptions): void {
  const router = useRouter();
  // Track whether we're waiting for the second key in a sequence
  const sequencePrefixRef = useRef<string | null>(null);
  const sequenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function clearSequence() {
      sequencePrefixRef.current = null;
      if (sequenceTimerRef.current) {
        clearTimeout(sequenceTimerRef.current);
        sequenceTimerRef.current = null;
      }
    }

    function handleKeyDown(e: KeyboardEvent) {
      const inEditable = isEditableTarget(e.target);
      const key = e.key.toLowerCase();
      const meta = e.metaKey || e.ctrlKey;

      // Cmd/Ctrl + K → command palette (works everywhere including inputs)
      if (meta && key === 'k') {
        e.preventDefault();
        onOpenCommandPalette();
        clearSequence();
        return;
      }

      // Cmd/Ctrl + / → shortcuts help
      if (meta && e.key === '/') {
        e.preventDefault();
        onOpenShortcutsHelp();
        clearSequence();
        return;
      }

      // Don't process further shortcuts when the user is typing
      if (inEditable) return;

      // Handle second key in a "G → X" sequence
      if (sequencePrefixRef.current === 'g') {
        clearSequence();
        switch (key) {
          case 'd': router.push('/'); return;
          case 'a': router.push('/agents'); return;
          case 't': router.push('/tasks'); return;
          case 's': router.push('/settings'); return;
        }
        // Unrecognized second key — fall through and handle it as a fresh input
      }

      // Single-key shortcuts
      if (key === 'g' && !meta) {
        // Start a sequence timer — if no second key arrives, cancel
        sequencePrefixRef.current = 'g';
        sequenceTimerRef.current = setTimeout(clearSequence, SEQUENCE_TIMEOUT_MS);
        return;
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      clearSequence();
    };
  }, [router, onOpenCommandPalette, onOpenShortcutsHelp]);
}
