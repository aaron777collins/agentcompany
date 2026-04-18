'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Header from '@/components/layout/Header';
import KanbanBoard from '@/components/tasks/KanbanBoard';
import { tasks as tasksApi } from '@/lib/api';
import { useCompanies, useActiveCompany } from '@/hooks/useCompany';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Modal from '@/components/ui/Modal';
import { PageSkeleton } from '@/components/ui/Spinner';
import type { Task, TaskPriority } from '@/lib/types';

export default function TasksPage() {
  const { companies } = useCompanies();
  const { activeCompanyId, setActiveCompanyId } = useActiveCompany();
  const companyId = activeCompanyId ?? companies[0]?.id;

  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const fetchTasks = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const res = await tasksApi.list({ company_id: companyId, page_size: 100 });
      setTasks(res.items);
    } catch {
      // Show empty board on error
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
        subtitle={`${tasks.length} tasks`}
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
          <PageSkeleton />
        ) : (
          <KanbanBoard initialTasks={tasks} />
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
      setTitle('');
      setDescription('');
      setPriority('medium');
      setError('');
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create task');
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
