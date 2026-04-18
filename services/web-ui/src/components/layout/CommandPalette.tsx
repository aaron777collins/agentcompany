'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { cx, debounce } from '@/lib/utils';
import { search as searchApi } from '@/lib/api';
import type { SearchResult } from '@/lib/types';

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

// Quick navigation links always available regardless of query
const quickLinks = [
  { label: 'Dashboard', href: '/', icon: '⚡' },
  { label: 'Agents', href: '/agents', icon: '🤖' },
  { label: 'Task Board', href: '/tasks', icon: '📋' },
  { label: 'Org Chart', href: '/org-chart', icon: '🗂️' },
  { label: 'Settings', href: '/settings', icon: '⚙️' },
];

const sourceIcon: Record<string, string> = {
  plane: '📋',
  outline: '📄',
  mattermost: '💬',
  agentcompany: '⚡',
};

const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose }) => {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when palette opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
    }
  }, [open]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const doSearch = useCallback(
    debounce(async (q: string) => {
      if (q.trim().length < 2) {
        setResults([]);
        return;
      }
      setLoading(true);
      try {
        const res = await searchApi.query({ q, limit: 8 });
        setResults(res.results);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300),
    [],
  );

  useEffect(() => {
    doSearch(query);
    setSelectedIndex(0);
  }, [query, doSearch]);

  const allItems = query.trim().length < 2 ? quickLinks : results.map((r) => ({
    label: r.title,
    href: r.url ?? '/search',
    icon: sourceIcon[r.source] ?? '🔍',
  }));

  const handleSelect = useCallback(
    (href: string) => {
      router.push(href);
      onClose();
    },
    [router, onClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, allItems.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter' && allItems[selectedIndex]) {
        handleSelect(allItems[selectedIndex].href);
      } else if (e.key === 'Escape') {
        onClose();
      }
    },
    [allItems, selectedIndex, handleSelect, onClose],
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 animate-fade-in">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Palette */}
      <div className="relative w-full max-w-xl rounded-2xl border border-surface-border bg-surface-1 shadow-modal animate-slide-down overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-surface-border">
          <svg className="w-4 h-4 text-text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search or navigate…"
            className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted text-sm outline-none"
          />
          {loading && (
            <svg className="w-4 h-4 text-accent animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          <kbd className="text-xs text-text-disabled border border-surface-border rounded px-1.5 py-0.5 font-mono">
            ESC
          </kbd>
        </div>

        {/* Results list */}
        <ul className="max-h-80 overflow-y-auto py-1">
          {allItems.length === 0 && query.length >= 2 && !loading && (
            <li className="px-4 py-8 text-center text-sm text-text-muted">
              No results for &quot;{query}&quot;
            </li>
          )}

          {allItems.length === 0 && query.length < 2 && (
            <li className="px-4 pt-2 pb-1 text-xs font-semibold text-text-muted uppercase tracking-wide">
              Quick Navigation
            </li>
          )}

          {allItems.map((item, index) => (
            <li key={`${item.href}-${index}`}>
              <button
                onClick={() => handleSelect(item.href)}
                className={cx(
                  'w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors',
                  index === selectedIndex
                    ? 'bg-accent/10 text-accent'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-3',
                )}
              >
                <span className="text-base leading-none">{item.icon}</span>
                <span className="flex-1 truncate">{item.label}</span>
                <svg className="w-3.5 h-3.5 text-text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </li>
          ))}
        </ul>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-surface-border flex items-center gap-3 text-xs text-text-muted">
          <span><kbd className="font-mono">↑↓</kbd> navigate</span>
          <span><kbd className="font-mono">↵</kbd> select</span>
          <span><kbd className="font-mono">esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
};

export default CommandPalette;
