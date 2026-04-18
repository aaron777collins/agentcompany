'use client';

import React, { useState, useCallback } from 'react';
import { tasks as tasksApi } from '@/lib/api';
import KanbanColumn from './KanbanColumn';
import type { Task, TaskStatus } from '@/lib/types';

interface KanbanBoardProps {
  initialTasks: Task[];
}

const COLUMN_ORDER: TaskStatus[] = ['backlog', 'todo', 'in_progress', 'review', 'done'];

// Cancelled tasks are intentionally excluded from the board — they are a
// terminal state and cluttering active columns with them harms readability.
// They remain accessible via the tasks API list endpoint with status filter.
const BOARD_STATUSES = new Set<TaskStatus>(COLUMN_ORDER);

const KanbanBoard: React.FC<KanbanBoardProps> = ({ initialTasks }) => {
  // Strip cancelled tasks on mount; they are terminal and live outside the board
  const [taskList, setTaskList] = useState<Task[]>(
    initialTasks.filter((t) => BOARD_STATUSES.has(t.status)),
  );
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTargetStatus, setDropTargetStatus] = useState<TaskStatus | null>(null);

  const tasksByStatus = COLUMN_ORDER.reduce(
    (acc, status) => {
      acc[status] = taskList.filter((t) => t.status === status);
      return acc;
    },
    {} as Record<TaskStatus, Task[]>,
  );

  const handleDragStart = useCallback((e: React.DragEvent, taskId: string) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', taskId);
    setDraggingId(taskId);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, status: TaskStatus) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDropTargetStatus(status);
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent, newStatus: TaskStatus) => {
      e.preventDefault();
      const taskId = e.dataTransfer.getData('text/plain');
      if (!taskId) return;

      const task = taskList.find((t) => t.id === taskId);
      if (!task || task.status === newStatus) {
        setDraggingId(null);
        setDropTargetStatus(null);
        return;
      }

      // Optimistic update — move immediately, revert on API failure
      setTaskList((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: newStatus } : t)),
      );
      setDraggingId(null);
      setDropTargetStatus(null);

      try {
        await tasksApi.update(taskId, { status: newStatus });
      } catch {
        // Revert on failure
        setTaskList((prev) =>
          prev.map((t) => (t.id === taskId ? { ...t, status: task.status } : t)),
        );
      }
    },
    [taskList],
  );

  const handleDragEnd = useCallback(() => {
    setDraggingId(null);
    setDropTargetStatus(null);
  }, []);

  return (
    <div
      className="flex gap-4 overflow-x-auto pb-6 min-h-[500px]"
      onDragEnd={handleDragEnd}
    >
      {COLUMN_ORDER.map((status) => (
        <KanbanColumn
          key={status}
          status={status}
          tasks={tasksByStatus[status]}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          draggingId={draggingId}
          isDropTarget={dropTargetStatus === status}
        />
      ))}
    </div>
  );
};

export default KanbanBoard;
