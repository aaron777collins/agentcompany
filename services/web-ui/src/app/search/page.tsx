'use client';

import React, { useState, useCallback, useEffect } from 'react';
import Header from '@/components/layout/Header';
import { search as searchApi } from '@/lib/api';
import { cx, debounce, timeAgo } from '@/lib/utils';
import Spinner from '@/components/ui/Spinner';
import type { SearchResult, SearchResultType } from '@/lib/types';

type FilterTab = 'all' | 'ticket' | 'document' | 'message';

const TABS: { label: string; value: FilterTab }[] = [
  { label: 'All', value: 'all' },
  { label: 'Tickets', value: 'ticket' },
  { label: 'Documents', value: 'document' },
  { label: 'Messages', value: 'message' },
];

const SOURCE_ICONS: Record<string, string> = {
  plane: '📋',
  outline: '📄',
  mattermost: '💬',
  agentcompany: '⚡',
};

const TYPE_COLORS: Record<SearchResultType, string> = {
  ticket: 'text-status-pending bg-status-pending/10 border-status-pending/20',
  document: 'text-accent bg-accent/10 border-accent/20',
  message: 'text-status-idle bg-status-idle/10 border-status-idle/20',
  agent: 'text-status-active bg-status-active/10 border-status-active/20',
  task: 'text-text-secondary bg-surface-3 border-surface-border',
};

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [activeTab, setActiveTab] = useState<FilterTab>('all');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [tookMs, setTookMs] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const doSearch = useCallback(
    debounce(async (q: string, tab: FilterTab) => {
      if (q.trim().length < 2) {
        setResults([]);
        setHasSearched(false);
        return;
      }
      setLoading(true);
      setHasSearched(true);
      try {
        const res = await searchApi.query({
          q,
          type: tab === 'all' ? 'all' : tab,
          limit: 30,
        });
        setResults(res.results);
        setTookMs(res.took_ms);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300),
    [],
  );

  useEffect(() => {
    doSearch(query, activeTab);
  }, [query, activeTab, doSearch]);

  return (
    <div className="flex flex-col h-full">
      <Header title="Search" />

      <div className="page-content max-w-3xl mx-auto w-full space-y-6">
        {/* Large search input */}
        <div className="relative">
          <div className="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted">
            {loading ? (
              <Spinner size="sm" />
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            )}
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            placeholder="Search tickets, documents, messages…"
            className="w-full h-14 pl-12 pr-4 rounded-2xl border border-surface-border bg-surface-1 text-text-primary placeholder:text-text-muted text-base focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent transition-all shadow-card"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Tab filters */}
        <div className="flex gap-1 border-b border-surface-border">
          {TABS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setActiveTab(value)}
              className={cx(
                'px-4 py-2 text-sm font-medium border-b-2 transition-all -mb-px',
                activeTab === value
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted hover:text-text-primary hover:border-surface-hover',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Results */}
        {!hasSearched && (
          <div className="empty-state py-20">
            <div className="empty-state-icon w-16 h-16">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">Search everything</p>
              <p className="text-xs text-text-muted mt-1">
                Tickets from Plane, documents from Outline, messages from Mattermost
              </p>
            </div>
          </div>
        )}

        {hasSearched && !loading && results.length === 0 && (
          <div className="text-center py-12">
            <p className="text-sm text-text-muted">
              No results for &quot;{query}&quot;{activeTab !== 'all' ? ` in ${activeTab}s` : ''}
            </p>
          </div>
        )}

        {results.length > 0 && (
          <div>
            <p className="text-xs text-text-muted mb-3">
              {results.length} result{results.length !== 1 ? 's' : ''} · {tookMs}ms
            </p>
            <div className="space-y-2">
              {results.map((result) => (
                <SearchResultCard key={result.id} result={result} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const SearchResultCard: React.FC<{ result: SearchResult }> = ({ result }) => (
  <a
    href={result.url ?? '#'}
    target="_blank"
    rel="noopener noreferrer"
    className="block rounded-xl border border-surface-border bg-surface-1 px-5 py-4 hover:border-surface-hover hover:shadow-card transition-all"
  >
    <div className="flex items-start gap-3">
      <span className="text-lg mt-0.5">{SOURCE_ICONS[result.source] ?? '🔍'}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <p className="text-sm font-medium text-text-primary truncate">{result.title}</p>
          <span className={cx(
            'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium shrink-0',
            TYPE_COLORS[result.type],
          )}>
            {result.type}
          </span>
        </div>
        <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">{result.snippet}</p>
        <div className="flex items-center gap-3 mt-2">
          <span className="text-xs text-text-muted capitalize">{result.source}</span>
          <span className="text-xs text-text-disabled">{timeAgo(result.created_at)}</span>
        </div>
      </div>
    </div>
  </a>
);
