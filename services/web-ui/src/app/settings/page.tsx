'use client';

import React, { useState, useEffect } from 'react';
import Header from '@/components/layout/Header';
import { integrations as integrationsApi, companies as companiesApi } from '@/lib/api';
import { useActiveCompany } from '@/hooks/useCompany';
import Card, { CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import { cx, formatDateTime } from '@/lib/utils';
import { SkeletonBlock } from '@/components/ui/Spinner';
import type { IntegrationHealth, Company } from '@/lib/types';

const STATUS_COLORS = {
  healthy: 'text-status-active',
  degraded: 'text-status-idle',
  down: 'text-status-error',
  unknown: 'text-text-muted',
};

const STATUS_DOTS = {
  healthy: 'bg-status-active',
  degraded: 'bg-status-idle',
  down: 'bg-status-error',
  unknown: 'bg-status-stopped',
};

export default function SettingsPage() {
  const [integrations, setIntegrations] = useState<IntegrationHealth[]>([]);
  const [integrationsLoading, setIntegrationsLoading] = useState(true);
  const { activeCompanyId } = useActiveCompany();

  useEffect(() => {
    integrationsApi
      .health()
      .then(setIntegrations)
      .catch(() => setIntegrations([]))
      .finally(() => setIntegrationsLoading(false));
  }, []);

  return (
    <div className="flex flex-col h-full">
      <Header title="Settings" subtitle="Platform configuration" />

      <div className="page-content max-w-2xl space-y-6">
        {/* Company settings */}
        {activeCompanyId && <CompanySettingsCard companyId={activeCompanyId} />}

        {/* Integration health */}
        <Card>
          <CardHeader>
            <CardTitle>Integration Health</CardTitle>
            <Button
              variant="ghost"
              size="xs"
              onClick={() => {
                setIntegrationsLoading(true);
                integrationsApi
                  .health()
                  .then(setIntegrations)
                  .catch(() => {})
                  .finally(() => setIntegrationsLoading(false));
              }}
            >
              Refresh
            </Button>
          </CardHeader>

          {integrationsLoading ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="flex items-center justify-between py-2">
                  <SkeletonBlock className="h-4 w-32" />
                  <SkeletonBlock className="h-5 w-20 rounded-full" />
                </div>
              ))}
            </div>
          ) : integrations.length === 0 ? (
            <p className="text-sm text-text-muted text-center py-6">
              Integration health data unavailable
            </p>
          ) : (
            <div className="space-y-1">
              {integrations.map((integration) => (
                <div
                  key={integration.name}
                  className="flex items-center justify-between py-3 border-b border-surface-border last:border-0"
                >
                  <div className="flex items-center gap-2.5">
                    <span className={cx('w-2 h-2 rounded-full', STATUS_DOTS[integration.status])} />
                    <div>
                      <p className="text-sm font-medium text-text-primary">
                        {integration.display_name}
                      </p>
                      {integration.error_message && (
                        <p className="text-xs text-status-error mt-0.5">{integration.error_message}</p>
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={cx('text-xs font-medium capitalize', STATUS_COLORS[integration.status])}>
                      {integration.status}
                    </p>
                    {integration.latency_ms !== null && (
                      <p className="text-xs text-text-muted">{integration.latency_ms}ms</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {integrations.length > 0 && (
            <p className="text-xs text-text-disabled mt-3">
              Last checked: {formatDateTime(integrations[0]?.last_checked_at)}
            </p>
          )}
        </Card>

        {/* Agent defaults */}
        <Card>
          <CardHeader>
            <CardTitle>Agent Defaults</CardTitle>
          </CardHeader>
          <div className="space-y-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
                Default LLM Provider
              </label>
              <select className="h-9 px-3 text-sm rounded-lg border border-surface-border bg-surface-2 text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent">
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="openai">OpenAI (GPT)</option>
                <option value="ollama">Ollama (local)</option>
              </select>
            </div>
            <Input
              label="Default Monthly Budget (USD)"
              type="number"
              min="0"
              step="0.01"
              placeholder="100.00"
              hint="Default budget applied to new agents. Can be overridden per agent."
            />
            <div className="flex justify-end">
              <Button variant="primary" size="sm">Save Defaults</Button>
            </div>
          </div>
        </Card>

        {/* User management placeholder */}
        <Card>
          <CardHeader>
            <CardTitle>User Management</CardTitle>
            <span className="text-xs bg-status-idle/10 text-status-idle border border-status-idle/20 rounded-full px-2 py-0.5 font-medium">
              Coming Soon
            </span>
          </CardHeader>
          <p className="text-sm text-text-muted">
            User management will be available after Keycloak SSO integration is configured.
            Users are currently managed directly in the Keycloak admin console at{' '}
            <code className="text-xs bg-surface-3 px-1.5 py-0.5 rounded font-mono text-text-secondary">
              http://localhost:8180
            </code>
            .
          </p>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Company settings card — editable name/description
// ---------------------------------------------------------------------------

const CompanySettingsCard: React.FC<{ companyId: string }> = ({ companyId }) => {
  const [company, setCompany] = useState<Company | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    companiesApi.get(companyId).then((c) => {
      setCompany(c);
      setName(c.name);
      setDescription(c.description ?? '');
    }).catch(() => {});
  }, [companyId]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await companiesApi.update(companyId, { name, description });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      // Surface error through form in a future iteration
    } finally {
      setSaving(false);
    }
  };

  if (!company) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Company Settings</CardTitle>
      </CardHeader>
      <form onSubmit={handleSave} className="space-y-4">
        <Input
          label="Company Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-surface-border bg-surface-2 text-text-primary placeholder:text-text-muted text-sm px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent transition-colors"
          />
        </div>
        <div className="flex justify-end gap-3">
          {saved && (
            <span className="text-xs text-status-active flex items-center gap-1">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
              Saved
            </span>
          )}
          <Button variant="primary" size="sm" type="submit" loading={saving}>
            Save Changes
          </Button>
        </div>
      </form>
    </Card>
  );
};
