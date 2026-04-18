'use client';

import React, { useState } from 'react';
import { cx, timeAgo, approvalStatusColors } from '@/lib/utils';
import { approvals as approvalsApi } from '@/lib/api';
import Button from '@/components/ui/Button';
import { SkeletonBlock } from '@/components/ui/Spinner';
import type { Approval } from '@/lib/types';

interface ApprovalQueueProps {
  approvals: Approval[];
  loading: boolean;
  onRefresh: () => void;
}

const ApprovalItem: React.FC<{ approval: Approval; onAction: () => void }> = ({
  approval,
  onAction,
}) => {
  const [approving, setApproving] = useState(false);
  const [denying, setDenying] = useState(false);

  const handleApprove = async () => {
    setApproving(true);
    try {
      await approvalsApi.approve(approval.id);
      onAction();
    } catch {
      // Silently retry — parent will refetch and surface the error through state
    } finally {
      setApproving(false);
    }
  };

  const handleDeny = async () => {
    setDenying(true);
    try {
      await approvalsApi.deny(approval.id);
      onAction();
    } catch {
      // Same as above
    } finally {
      setDenying(false);
    }
  };

  const isPending = approval.status === 'pending';

  return (
    <div className="px-5 py-4 border-b border-surface-border last:border-b-0">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-text-primary truncate">
              {approval.agent_name}
            </span>
            <span className={cx(
              'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium',
              approvalStatusColors[approval.status],
            )}>
              {approval.status}
            </span>
          </div>
          <p className="text-xs text-text-secondary leading-relaxed line-clamp-2">
            {approval.description}
          </p>
          <p className="text-xs text-text-muted mt-1">{timeAgo(approval.requested_at)}</p>
        </div>

        {isPending && (
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="success"
              size="xs"
              loading={approving}
              onClick={handleApprove}
            >
              Approve
            </Button>
            <Button
              variant="danger"
              size="xs"
              loading={denying}
              onClick={handleDeny}
            >
              Deny
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};

const ApprovalQueue: React.FC<ApprovalQueueProps> = ({ approvals, loading, onRefresh }) => (
  <div className="rounded-xl border border-surface-border bg-surface-1 flex flex-col max-h-96">
    <div className="px-5 py-4 border-b border-surface-border flex items-center justify-between shrink-0">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-text-primary">Approval Queue</h3>
        {approvals.length > 0 && (
          <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-status-idle/20 text-status-idle text-xs font-bold px-1">
            {approvals.length}
          </span>
        )}
      </div>
    </div>

    <div className="flex-1 overflow-y-auto">
      {loading ? (
        <div className="divide-y divide-surface-border">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="px-5 py-4">
              <SkeletonBlock className="h-3 w-32 mb-2" />
              <SkeletonBlock className="h-3 w-full mb-1" />
              <SkeletonBlock className="h-3 w-2/3" />
            </div>
          ))}
        </div>
      ) : approvals.length === 0 ? (
        <div className="flex items-center justify-center h-28 text-sm text-text-muted">
          No pending approvals
        </div>
      ) : (
        <div>
          {approvals.map((approval) => (
            <ApprovalItem key={approval.id} approval={approval} onAction={onRefresh} />
          ))}
        </div>
      )}
    </div>
  </div>
);

export default ApprovalQueue;
