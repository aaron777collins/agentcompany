'use client';

/**
 * ActivityFeed — real-time SSE event display.
 *
 * Events arrive from useSSE and are prepended to the list. Each new item
 * animates in from the top via CSS `animate-slide-down`. The list is capped
 * at 50 displayed entries (older events are silently dropped).
 */

import React from 'react';
import { cx, timeAgo } from '@/lib/utils';
import type { Event, EventType } from '@/lib/types';

interface ActivityFeedProps {
  events: Event[];
  connected: boolean;
  error: string | null;
}

// Maps event type to a visual indicator: SVG path, dot colour, and display label
const eventTypeConfig: Record<
  EventType,
  { color: string; label: string; iconPath: string }
> = {
  'agent.started':       { color: 'text-status-active', label: 'Started',       iconPath: 'M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z' },
  'agent.stopped':       { color: 'text-status-stopped', label: 'Stopped',      iconPath: 'M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z' },
  'agent.error':         { color: 'text-status-error',   label: 'Error',        iconPath: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z' },
  'agent.task_assigned': { color: 'text-accent',         label: 'Assigned',     iconPath: 'M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244' },
  'task.created':        { color: 'text-status-pending', label: 'Task Created', iconPath: 'M12 4.5v15m7.5-7.5h-15' },
  'task.status_changed': { color: 'text-text-secondary', label: 'Status',       iconPath: 'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99' },
  'task.completed':      { color: 'text-status-active',  label: 'Completed',    iconPath: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
  'approval.requested':  { color: 'text-status-idle',    label: 'Approval',     iconPath: 'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z' },
  'approval.granted':    { color: 'text-status-active',  label: 'Approved',     iconPath: 'M4.5 12.75l6 6 9-13.5' },
  'approval.denied':     { color: 'text-status-error',   label: 'Denied',       iconPath: 'M6 18L18 6M6 6l12 12' },
  'token.budget_warning':{ color: 'text-status-idle',    label: 'Budget',       iconPath: 'M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
  'system.health_change':{ color: 'text-text-muted',     label: 'System',       iconPath: 'M21 10.5h.375a.375.375 0 01.375.375v.375M21 10.5V9.75A2.25 2.25 0 0018.75 7.5h-1.875a.375.375 0 00-.375.375v.375M21 10.5v.375a.375.375 0 01-.375.375H18M3 10.5h-.375A.375.375 0 002.25 10.875v.375M3 10.5V9.75A2.25 2.25 0 015.25 7.5h1.875c.207 0 .375.168.375.375v.375M3 10.5v.375c0 .207.168.375.375.375H6M12 3v18' },
};

// Hard cap on displayed events — prevents the DOM from growing unbounded
const MAX_DISPLAYED = 50;

const ActivityFeed: React.FC<ActivityFeedProps> = ({ events, connected, error }) => {
  const displayed = events.slice(0, MAX_DISPLAYED);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-1 flex flex-col h-full max-h-[28rem]">
      {/* Header */}
      <div className="px-5 py-4 border-b border-surface-border flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-text-primary">Activity Feed</h3>
        <div className="flex items-center gap-1.5">
          <span
            className={cx(
              'w-1.5 h-1.5 rounded-full',
              connected ? 'bg-status-active animate-pulse' : 'bg-status-stopped',
            )}
          />
          <span className="text-xs text-text-muted">{connected ? 'Live' : 'Disconnected'}</span>
        </div>
      </div>

      {/* Reconnecting banner */}
      {error && !connected && (
        <div className="px-5 py-2.5 text-xs text-status-idle border-b border-surface-border bg-status-idle/5 shrink-0">
          {error}
        </div>
      )}

      {/* Feed */}
      <div className="flex-1 overflow-y-auto">
        {displayed.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-sm text-text-muted">
            <svg className="w-8 h-8 text-text-disabled" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
            <span>{connected ? 'Waiting for events…' : 'Connecting to event stream…'}</span>
          </div>
        ) : (
          <ul className="divide-y divide-surface-border">
            {displayed.map((event, index) => {
              const config = eventTypeConfig[event.type] ?? {
                color: 'text-text-muted',
                label: event.type,
                iconPath: 'M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z',
              };

              return (
                <li
                  key={event.id}
                  // The first item (newest) gets a slide-in animation
                  className={cx(
                    'px-5 py-3 hover:bg-surface-3/40 transition-colors',
                    index === 0 ? 'animate-slide-down' : '',
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    {/* Event type icon */}
                    <svg
                      className={cx('w-3.5 h-3.5 shrink-0 mt-0.5', config.color)}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d={config.iconPath} />
                    </svg>

                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-text-secondary leading-relaxed">
                        {event.message}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                        <span className={cx('text-xs font-medium', config.color)}>
                          {config.label}
                        </span>
                        {event.actor_name && (
                          <span className="text-xs text-text-muted">· {event.actor_name}</span>
                        )}
                        <span className="text-xs text-text-disabled ml-auto shrink-0">
                          {timeAgo(event.created_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
};

export default ActivityFeed;
