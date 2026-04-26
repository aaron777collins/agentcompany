'use client';

/**
 * Keyboard shortcuts help modal.
 *
 * Displays a clean reference of every registered shortcut.
 * Triggered by Cmd/Ctrl + / or from the command palette.
 */

import React from 'react';
import Modal from '@/components/ui/Modal';
import { SHORTCUTS } from '@/hooks/useKeyboardShortcuts';
import { cx } from '@/lib/utils';

interface KeyboardShortcutsProps {
  open: boolean;
  onClose: () => void;
}

// Render a key badge with OS-aware modifier symbol
function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd
      className={cx(
        'inline-flex items-center justify-center min-w-[1.75rem] h-7 px-1.5',
        'rounded-md border border-surface-border bg-surface-3',
        'text-xs font-mono font-medium text-text-secondary',
        'shadow-[0_1px_0_0_theme(colors.surface.border)]',
      )}
    >
      {children}
    </kbd>
  );
}

const KeyboardShortcuts: React.FC<KeyboardShortcutsProps> = ({ open, onClose }) => (
  <Modal open={open} onClose={onClose} title="Keyboard Shortcuts" size="md">
    <div className="space-y-1">
      {SHORTCUTS.map((shortcut, index) => {
        const keys = Array.isArray(shortcut.keys) ? shortcut.keys : [shortcut.keys];

        // Display the modifier prefix for single-key Cmd shortcuts
        const isMetaShortcut = shortcut.keys === 'k' || shortcut.keys === '/';

        return (
          <div
            key={index}
            className="flex items-center justify-between py-2.5 border-b border-surface-border last:border-0"
          >
            <span className="text-sm text-text-secondary">{shortcut.label}</span>

            <div className="flex items-center gap-1.5 shrink-0">
              {isMetaShortcut && (
                <>
                  <Kbd>
                    {/* Renders ⌘ on macOS hint; both Ctrl and Cmd work at runtime */}
                    ⌘
                  </Kbd>
                  <span className="text-text-muted text-xs">+</span>
                </>
              )}

              {keys.map((k, ki) => (
                <React.Fragment key={ki}>
                  {ki > 0 && (
                    <span className="text-text-muted text-xs">then</span>
                  )}
                  <Kbd>
                    {k === 'Escape' ? 'Esc' : k.toUpperCase()}
                  </Kbd>
                </React.Fragment>
              ))}
            </div>
          </div>
        );
      })}
    </div>

    <p className="mt-4 text-xs text-text-muted">
      Shortcuts are disabled when a text input is focused. Press{' '}
      <kbd className="font-mono">Esc</kbd> to close any open modal or palette.
    </p>
  </Modal>
);

export default KeyboardShortcuts;
