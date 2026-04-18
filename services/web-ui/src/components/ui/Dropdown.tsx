'use client';

import React, { useState, useRef, useEffect } from 'react';
import { cx } from '@/lib/utils';

export interface DropdownItem {
  label: string;
  value: string;
  icon?: React.ReactNode;
  danger?: boolean;
  disabled?: boolean;
}

interface DropdownProps {
  trigger: React.ReactNode;
  items: DropdownItem[];
  onSelect: (value: string) => void;
  align?: 'left' | 'right';
}

const Dropdown: React.FC<DropdownProps> = ({ trigger, items, onSelect, align = 'left' }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close when clicking outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => setOpen((o) => !o)}>{trigger}</div>

      {open && (
        <div
          className={cx(
            'absolute z-40 mt-1.5 min-w-[160px] rounded-xl border border-surface-border',
            'bg-surface-2 shadow-elevated py-1 animate-slide-down',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          {items.map((item) => (
            <button
              key={item.value}
              disabled={item.disabled}
              onClick={() => {
                onSelect(item.value);
                setOpen(false);
              }}
              className={cx(
                'w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors',
                item.danger
                  ? 'text-status-error hover:bg-status-error/10'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-3',
                item.disabled && 'opacity-50 cursor-not-allowed',
              )}
            >
              {item.icon && <span className="shrink-0 w-4">{item.icon}</span>}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default Dropdown;
