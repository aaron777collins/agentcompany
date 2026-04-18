'use client';

import React from 'react';
import { cx, timeAgo } from '@/lib/utils';
import type { Event, EventType } from '@/lib/types';

interface ActivityFeedProps {
  events: Event[];
  connected: boolean;
  error: string | null;
}

const eventTypeConfig: Record<EventType, { color: string; label: string }> = {
  'agent.started': { color: 'text-status-active', label: 'Started' },
  'agent.stopped': { color: 'text-status-stopped', label: 'Stopped' },
  'agent.error': { color: 'text-status-error', label: 'Error' },
  'agent.task_assigned': { color: 'text-accent', label: 'Assigned' },
  'task.created': { color: 'text-status-pending', label: 'Task Created' },
  'task.status_changed': { color: 'text-text-secondary', label: 'Status Changed' },
  'task.completed': { color: 'text-status-active', label: 'Completed' },
  'approval.requested': { color: 'text-status-idle', label: 'Approval' },
  'approval.granted': { color: 'text-status-active', label: 'Approved' },
  'approval.denied': { color: 'text-status-error', label: 'Denied' },
  'token.budget_warning': { color: 'text-status-idle', label: 'Budget Warning' },
  'system.health_change': { color: 'text-text-muted', label: 'System' },
};

const ActivityFeed: React.FC<ActivityFeedProps> = ({ events, connected, error }) => (
  <div className="rounded-xl border border-surface-border bg-surface-1 flex flex-col h-full max-h-96">
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

    {/* Feed */}
    <div className="flex-1 overflow-y-auto">
      {error && !connected && (
        <div className="px-5 py-3 text-xs text-status-idle border-b border-surface-border bg-status-idle/5">
          {error}
        </div>
      )}

      {events.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-sm text-text-muted">
          {connected ? 'Waiting for events…' : 'Connecting to event stream…'}
        </div>
      ) : (
        <ul className="divide-y divide-surface-border">
          {events.map((event) => {
            const config = eventTypeConfig[event.type] ?? {
              color: 'text-text-muted',
              label: event.type,
            };

            return (
              <li key={event.id} className="px-5 py-3 hover:bg-surface-3/40 transition-colors">
                <div className="flex items-start gap-2.5">
                  {/* Type indicator dot */}
                  <span className={cx('mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 bg-current', config.color)} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-text-secondary leading-relaxed truncate">
                      {event.message}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
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

export default ActivityFeed;
