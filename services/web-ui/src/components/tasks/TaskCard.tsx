'use client';

import React from 'react';
import { cx, truncate, initials, stringToColor, taskPriorityColors, taskPriorityIcons } from '@/lib/utils';
import type { Task } from '@/lib/types';

interface TaskCardProps {
  task: Task;
  isDragging?: boolean;
}

const TaskCard: React.FC<TaskCardProps> = ({ task, isDragging = false }) => {
  const priorityColor = taskPriorityColors[task.priority];
  const priorityIcon = taskPriorityIcons[task.priority];

  return (
    <div
      className={cx(
        'rounded-lg border border-surface-border bg-surface-2 p-3.5',
        'cursor-grab active:cursor-grabbing select-none',
        'transition-all duration-150 hover:border-surface-hover hover:shadow-card',
        isDragging && 'shadow-elevated rotate-1 opacity-90',
      )}
    >
      {/* Priority + Labels row */}
      <div className="flex items-center gap-1.5 mb-2 flex-wrap">
        <span className={cx('text-xs font-bold', priorityColor)} title={task.priority}>
          {priorityIcon}
        </span>
        {task.labels.map((label) => (
          <span
            key={label.id}
            className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
            style={{
              backgroundColor: `${label.color}20`,
              color: label.color,
              border: `1px solid ${label.color}40`,
            }}
          >
            {label.name}
          </span>
        ))}
      </div>

      {/* Title */}
      <p className="text-sm font-medium text-text-primary leading-snug">
        {truncate(task.title, 80)}
      </p>

      {/* Footer */}
      {task.assignee_name && (
        <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-surface-border/60">
          <div className="flex items-center gap-1.5">
            <div
              className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold text-white"
              style={{ backgroundColor: stringToColor(task.assignee_name) }}
            >
              {initials(task.assignee_name).charAt(0)}
            </div>
            <span className="text-xs text-text-muted truncate max-w-[100px]">
              {task.assignee_name}
            </span>
          </div>
          <span className="text-xs font-mono text-text-disabled">
            {task.id.split('_')[1]?.slice(-6) ?? ''}
          </span>
        </div>
      )}
    </div>
  );
};

export default TaskCard;
