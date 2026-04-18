'use client';

import React from 'react';
import { cx, taskStatusLabels } from '@/lib/utils';
import TaskCard from './TaskCard';
import type { Task, TaskStatus } from '@/lib/types';

interface KanbanColumnProps {
  status: TaskStatus;
  tasks: Task[];
  onDragOver: (e: React.DragEvent, status: TaskStatus) => void;
  onDrop: (e: React.DragEvent, status: TaskStatus) => void;
  onDragStart: (e: React.DragEvent, taskId: string) => void;
  draggingId: string | null;
  isDropTarget: boolean;
}

// Column accent colors by status — visually distinct at a glance
const columnColors: Record<TaskStatus, { header: string; count: string }> = {
  backlog: {
    header: 'text-text-muted',
    count: 'bg-surface-3 text-text-muted',
  },
  todo: {
    header: 'text-text-secondary',
    count: 'bg-surface-3 text-text-secondary',
  },
  in_progress: {
    header: 'text-accent',
    count: 'bg-accent/10 text-accent',
  },
  review: {
    header: 'text-status-idle',
    count: 'bg-status-idle/10 text-status-idle',
  },
  done: {
    header: 'text-status-active',
    count: 'bg-status-active/10 text-status-active',
  },
};

const KanbanColumn: React.FC<KanbanColumnProps> = ({
  status,
  tasks,
  onDragOver,
  onDrop,
  onDragStart,
  draggingId,
  isDropTarget,
}) => {
  const colors = columnColors[status];
  const label = taskStatusLabels[status];

  return (
    <div
      className={cx(
        'flex flex-col rounded-xl border bg-surface-1 min-w-[240px] w-72 flex-shrink-0 transition-colors',
        isDropTarget
          ? 'border-accent/40 bg-accent/5'
          : 'border-surface-border',
      )}
      onDragOver={(e) => onDragOver(e, status)}
      onDrop={(e) => onDrop(e, status)}
    >
      {/* Column header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
        <span className={cx('text-xs font-semibold uppercase tracking-wide', colors.header)}>
          {label}
        </span>
        <span className={cx('text-xs font-bold rounded-full px-2 py-0.5', colors.count)}>
          {tasks.length}
        </span>
      </div>

      {/* Task cards */}
      <div
        className={cx(
          'flex-1 p-3 space-y-2 overflow-y-auto min-h-[80px]',
          isDropTarget && tasks.length === 0 && 'flex items-center justify-center',
        )}
      >
        {tasks.length === 0 && !isDropTarget && (
          <p className="text-xs text-text-disabled text-center py-4 italic">
            No tasks
          </p>
        )}

        {isDropTarget && tasks.length === 0 && (
          <p className="text-xs text-accent text-center italic">Drop here</p>
        )}

        {tasks.map((task) => (
          <div
            key={task.id}
            draggable
            onDragStart={(e) => onDragStart(e, task.id)}
            className={cx(
              'transition-opacity duration-150',
              draggingId === task.id ? 'opacity-50' : 'opacity-100',
            )}
          >
            <TaskCard task={task} isDragging={draggingId === task.id} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default KanbanColumn;
