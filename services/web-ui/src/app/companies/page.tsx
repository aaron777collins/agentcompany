'use client';

import React, { useState } from 'react';
import Header from '@/components/layout/Header';
import { useCompanies } from '@/hooks/useCompany';
import { companies as companiesApi } from '@/lib/api';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Modal from '@/components/ui/Modal';
import { SkeletonBlock } from '@/components/ui/Spinner';
import { formatDate, stringToColor, initials } from '@/lib/utils';
import type { Company } from '@/lib/types';

export default function CompaniesPage() {
  const { companies, loading, refetch } = useCompanies();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="flex flex-col h-full">
      <Header
        title="Companies"
        subtitle="Manage AI-powered companies"
        actions={
          <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
            + New Company
          </Button>
        }
      />

      <div className="page-content">
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="rounded-xl border border-surface-border bg-surface-1 p-5">
                <SkeletonBlock className="w-12 h-12 rounded-xl mb-4" />
                <SkeletonBlock className="h-4 w-40 mb-2" />
                <SkeletonBlock className="h-3 w-full mb-1" />
                <SkeletonBlock className="h-3 w-3/4" />
              </div>
            ))}
          </div>
        ) : companies.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                  d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">No companies yet</p>
              <p className="text-xs text-text-muted mt-1">Create your first AI-powered company</p>
            </div>
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              Create Company
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {companies.map((company) => (
              <CompanyCard key={company.id} company={company} />
            ))}
          </div>
        )}
      </div>

      <CreateCompanyModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); refetch(); }}
      />
    </div>
  );
}

const CompanyCard: React.FC<{ company: Company }> = ({ company }) => (
  <Card hoverable>
    <div className="flex items-start gap-4">
      <div
        className="w-12 h-12 rounded-xl flex items-center justify-center text-base font-bold text-white shrink-0"
        style={{ backgroundColor: stringToColor(company.name) }}
      >
        {initials(company.name)}
      </div>
      <div className="flex-1 min-w-0">
        <h3 className="font-semibold text-text-primary truncate">{company.name}</h3>
        {company.industry && (
          <p className="text-xs text-text-muted">{company.industry}</p>
        )}
      </div>
    </div>

    {company.description && (
      <p className="text-sm text-text-secondary mt-3 line-clamp-2 leading-relaxed">
        {company.description}
      </p>
    )}

    <div className="flex items-center justify-between mt-4 pt-3 border-t border-surface-border">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-status-active" />
          <span className="text-xs text-text-muted">{company.active_agent_count} active</span>
        </div>
        <span className="text-xs text-text-disabled">{company.agent_count} agents</span>
      </div>
      <span className="text-xs text-text-muted">{formatDate(company.created_at)}</span>
    </div>
  </Card>
);

interface CreateCompanyModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

const CreateCompanyModal: React.FC<CreateCompanyModalProps> = ({ open, onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [industry, setIndustry] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Company name is required');
      return;
    }
    setLoading(true);
    try {
      await companiesApi.create({ name: name.trim(), description: description || undefined, industry: industry || undefined });
      setName('');
      setDescription('');
      setIndustry('');
      setError('');
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create company');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="New Company" size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Company Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Acme Corp"
          required
          error={error}
        />
        <Input
          label="Industry"
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          placeholder="Technology, Finance, etc."
        />
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="What does this company do?"
            className="w-full rounded-lg border border-surface-border bg-surface-2 text-text-primary placeholder:text-text-muted text-sm px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent transition-colors"
          />
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="ghost" size="sm" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" loading={loading}>
            Create Company
          </Button>
        </div>
      </form>
    </Modal>
  );
};
