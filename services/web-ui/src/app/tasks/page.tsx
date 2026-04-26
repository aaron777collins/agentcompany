'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Header from '@/components/layout/Header';
import KanbanBoard from '@/components/tasks/KanbanBoard';
import { tasks as tasksApi } from '@/lib/api';
import { useCompanies, useActiveCompany } from '@/hooks/useCompany';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Modal from '@/components/ui/Modal';
import { SkeletonBlock } from '@/components/ui/Spinner';
import { toast } from '@/hooks/useToast';
import type { Task, TaskPriority } from '@/lib/types';

// ---------------------------------------------------------------------------
// Kanban loading skeleton — mirrors the column structure
// ---------------------------------------------------------------------------

function KanbanSkeleton() {
  return (
    <div className="flex gap-4 h-full overflow-x-auto pb-4">
      {[...Array(5)].map((_, col) => (
        <div
          key={col}
          className="flex-shrink-0 w-72 rounded-xl border border-surface-border bg-surface-1 flex flex-col"
        >
          {/* Column header */}
          <div className="px-4 py-3 border-b border-surface-border flex items-center gap-2">
            <SkeletonBlock className="h-4 w-24" />
            <SkeletonBlock className="h-5 w-6 rounded-full ml-auto" />
          </div>
          {/* Cards */}
          <div className="flex-1 p-3 space-y-2 overflow-y-auto">
            {[...Array(col === 2 ? 4 : col === 0 ? 3 : 2)].map((_, i) => (
              <div
                key={i}
                className="rounded-lg border border-surface-border bg-surface-2 p-3 space-y-2"
              >
                <SkeletonBlock className="h-3.5 w-full" />
                <SkeletonBlock className="h-3 w-4/5" />
                <div className="flex items-center gap-2 pt-1">
                  <SkeletonBlock className="h-5 w-12 rounded-full" />
                  <SkeletonBlock className="h-5 w-16 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TasksPage() {
  const { companies } = useCompanies();
  const { activeCompanyId, setActiveCompanyId } = useActiveCompany();
  const companyId = activeCompanyId ?? companies[0]?.id;

  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const fetchTasks = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await tasksApi.list({ company_id: companyId, page_size: 100 });
      setTasks(res.items);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load tasks';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  const handleRetry = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (!companyId) return;
      const res = await tasksApi.list({ company_id: companyId, page_size: 100 });
      setTasks(res.items);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load tasks';
      setError(msg);
      toast.error('Could not load tasks', msg);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  return (
    <div className="flex flex-col h-full">
      <Header
        title="Task Board"
        subtitle={loading ? undefined : `${tasks.length} tasks`}
        actions={
          <div className="flex items-center gap-2">
            {companies.length > 1 && (
              <select
                value={companyId}
                onChange={(e) => setActiveCompanyId(e.target.value)}
                className="h-8 px-3 text-xs rounded-lg border border-surface-border bg-surface-2 text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
              >
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            )}
            <Button
              variant="primary"
              size="sm"
              disabled={!companyId}
              onClick={() => setCreateOpen(true)}
            >
              + New Task
            </Button>
          </div>
        }
      />

      <div className="flex-1 overflow-hidden px-6 pt-4 pb-6">
        {loading ? (
          <KanbanSkeleton />
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <div className="rounded-2xl border border-status-error/20 bg-status-error/5 p-10 text-center max-w-sm w-full space-y-4">
              <div className="w-14 h-14 rounded-2xl bg-status-error/10 flex items-center justify-center mx-auto">
                <svg className="w-7 h-7 text-status-error" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                    d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-semibold text-status-error">Could not load tasks</p>
                <p className="text-xs text-text-muted mt-1.5">{error}</p>
              </div>
              <Button variant="danger" size="sm" onClick={handleRetry}>
                Retry
              </Button>
            </div>
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <div className="empty-state">
              <div className="empty-state-icon w-16 h-16">
                <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-text-primary">No tasks yet</p>
                <p className="text-xs text-text-muted mt-1">Create your first task to start tracking work</p>
              </div>
              {companyId && (
                <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                  + Create first task
                </Button>
              )}
            </div>
          </div>
        ) : (
          // Horizontal scroll wrapper for Kanban on small screens
          <div className="kanban-scroll h-full">
            <KanbanBoard initialTasks={tasks} />
          </div>
        )}
      </div>

      {companyId && (
        <CreateTaskModal
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          companyId={companyId}
          onCreated={() => { setCreateOpen(false); fetchTasks(); }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create task modal
// ---------------------------------------------------------------------------

interface CreateTaskModalProps {
  open: boolean;
  onClose: () => void;
  companyId: string;
  onCreated: () => void;
}

const PRIORITIES: TaskPriority[] = ['critical', 'high', 'medium', 'low'];

const CreateTaskModal: React.FC<CreateTaskModalProps> = ({
  open,
  onClose,
  companyId,
  onCreated,
}) => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('Task title is required');
      return;
    }
    setLoading(true);
    try {
      await tasksApi.create({
        company_id: companyId,
        title: title.trim(),
        description: description || undefined,
        priority,
        status: 'backlog',
      });
      toast.success('Task created', `"${title.trim()}" added to the backlog`);
      setTitle('');
      setDescription('');
      setPriority('medium');
      setError('');
      onCreated();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create task';
      setError(msg);
      toast.error('Failed to create task', msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="New Task" size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What needs to be done?"
          required
          error={error}
        />

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Optional details…"
            className="w-full rounded-lg border border-surface-border bg-surface-2 text-text-primary placeholder:text-text-muted text-sm px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent transition-colors"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
            Priority
          </label>
          <div className="flex gap-2">
            {PRIORITIES.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPriority(p)}
                className={`flex-1 py-1.5 text-xs font-medium rounded-lg border transition-all capitalize ${
                  priority === p
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-surface-border text-text-muted hover:text-text-secondary hover:border-surface-hover'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="ghost" size="sm" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" loading={loading}>
            Create Task
          </Button>
        </div>
      </form>
    </Modal>
  );
};
