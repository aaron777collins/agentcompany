'use client';

import React from 'react';
import { cx } from '@/lib/utils';
import Button from '@/components/ui/Button';

interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  onCommandPaletteOpen?: () => void;
}

const Header: React.FC<HeaderProps> = ({ title, subtitle, actions, onCommandPaletteOpen }) => (
  <header className="sticky top-0 z-20 flex items-center justify-between h-14 px-6 border-b border-surface-border bg-surface/80 backdrop-blur-md shrink-0">
    {/* Page title */}
    <div className="flex items-baseline gap-2">
      <h1 className="text-base font-semibold text-text-primary">{title}</h1>
      {subtitle && (
        <span className="text-sm text-text-muted hidden sm:block">{subtitle}</span>
      )}
    </div>

    {/* Right side actions */}
    <div className="flex items-center gap-2">
      {actions}

      {/* Cmd+K search shortcut hint */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onCommandPaletteOpen}
        className="hidden md:flex gap-1.5 text-text-muted"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <span className="text-xs">Search</span>
        <kbd className={cx(
          'inline-flex items-center gap-0.5 rounded border border-surface-border',
          'px-1.5 py-0.5 text-xs font-mono text-text-disabled'
        )}>
          ⌘K
        </kbd>
      </Button>
    </div>
  </header>
);

export default Header;
