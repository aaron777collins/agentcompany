'use client';

import React, { useState, useEffect } from 'react';
import Header from '@/components/layout/Header';
import OrgTree from '@/components/org-chart/OrgTree';
import { orgChart as orgChartApi } from '@/lib/api';
import { useCompanies, useActiveCompany } from '@/hooks/useCompany';
import { PageSkeleton } from '@/components/ui/Spinner';
import type { OrgNode } from '@/lib/types';

export default function OrgChartPage() {
  const { companies } = useCompanies();
  const { activeCompanyId, setActiveCompanyId } = useActiveCompany();
  const companyId = activeCompanyId ?? companies[0]?.id;

  const [orgRoot, setOrgRoot] = useState<OrgNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId) return;
    setLoading(true);
    setError(null);
    orgChartApi
      .get(companyId)
      .then(setOrgRoot)
      .catch((err) => setError(err.message ?? 'Failed to load org chart'))
      .finally(() => setLoading(false));
  }, [companyId]);

  return (
    <div className="flex flex-col h-full">
      <Header
        title="Org Chart"
        subtitle="Company hierarchy"
        actions={
          companies.length > 1 ? (
            <select
              value={companyId}
              onChange={(e) => setActiveCompanyId(e.target.value)}
              className="h-8 px-3 text-xs rounded-lg border border-surface-border bg-surface-2 text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
            >
              {companies.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          ) : undefined
        }
      />

      <div className="flex-1 overflow-hidden">
        {loading && <PageSkeleton />}

        {error && (
          <div className="page-content">
            <div className="rounded-xl border border-status-error/20 bg-status-error/5 p-6 text-center">
              <p className="text-sm text-status-error">{error}</p>
              <p className="text-xs text-text-muted mt-1">
                Make sure at least one company with roles exists.
              </p>
            </div>
          </div>
        )}

        {!loading && !error && !orgRoot && (
          <div className="empty-state">
            <p className="text-sm text-text-muted">
              {companyId ? 'No org chart data available.' : 'Select a company to view its org chart.'}
            </p>
          </div>
        )}

        {!loading && orgRoot && (
          <div className="overflow-auto h-full">
            <div className="p-6">
              {/* Legend */}
              <div className="flex items-center gap-4 mb-6 flex-wrap">
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">Legend:</p>
                {[
                  { label: 'Active', color: 'bg-status-active' },
                  { label: 'Idle', color: 'bg-status-idle' },
                  { label: 'Error', color: 'bg-status-error' },
                  { label: 'Stopped', color: 'bg-status-stopped' },
                ].map(({ label, color }) => (
                  <div key={label} className="flex items-center gap-1.5">
                    <span className={`w-2.5 h-2.5 rounded-full ${color}`} />
                    <span className="text-xs text-text-muted">{label}</span>
                  </div>
                ))}
                <p className="text-xs text-text-disabled ml-auto">Click a node to view agent details</p>
              </div>

              <OrgTree root={orgRoot} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
