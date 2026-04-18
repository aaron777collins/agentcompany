'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { cx, initials, stringToColor, agentStatusColors } from '@/lib/utils';
import type { OrgNode } from '@/lib/types';

interface OrgTreeProps {
  root: OrgNode;
}

interface OrgNodeCardProps {
  node: OrgNode;
  depth: number;
}

const OrgNodeCard: React.FC<OrgNodeCardProps> = ({ node, depth }) => {
  const router = useRouter();
  const isAgent = node.type === 'agent';
  const statusColors = isAgent && node.status !== 'human'
    ? agentStatusColors[node.status as Exclude<OrgNode['status'], 'human'>]
    : null;

  const handleClick = () => {
    if (node.agent_id) {
      router.push(`/agents/${node.agent_id}`);
    }
  };

  return (
    <div
      onClick={handleClick}
      role={node.agent_id ? 'button' : undefined}
      tabIndex={node.agent_id ? 0 : undefined}
      onKeyDown={(e) => { if (e.key === 'Enter' && node.agent_id) handleClick(); }}
      className={cx(
        'flex flex-col items-center gap-1 rounded-xl border px-4 py-3',
        'bg-surface-1 border-surface-border min-w-[120px] max-w-[160px]',
        node.agent_id && 'cursor-pointer hover:border-accent hover:shadow-glow transition-all duration-150',
        depth === 0 && 'border-accent/30 shadow-glow',
      )}
    >
      {/* Avatar */}
      <div className="relative">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold text-white"
          style={{ backgroundColor: stringToColor(node.name) }}
        >
          {initials(node.name)}
        </div>
        {statusColors && (
          <span
            className={cx(
              'absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-surface-1',
              statusColors.dot,
            )}
          />
        )}
      </div>

      {/* Info */}
      <div className="text-center min-w-0 w-full">
        <p className="text-xs font-semibold text-text-primary truncate">{node.name}</p>
        <p className="text-xs text-text-muted truncate">{node.role}</p>
        {isAgent && (
          <p className={cx('text-xs mt-0.5', statusColors?.text ?? 'text-text-muted')}>
            {node.status}
          </p>
        )}
      </div>
    </div>
  );
};

// Recursively renders the tree with vertical connectors
const TreeLevel: React.FC<{ nodes: OrgNode[]; depth: number }> = ({ nodes, depth }) => {
  if (nodes.length === 0) return null;

  return (
    <div className="flex gap-6 justify-center">
      {nodes.map((node) => (
        <div key={node.id} className="flex flex-col items-center gap-0">
          <OrgNodeCard node={node} depth={depth} />

          {/* Connector and children */}
          {node.children.length > 0 && (
            <>
              {/* Vertical line down from parent */}
              <div className="w-px h-6 bg-surface-border" />
              {/* Horizontal bar spanning children */}
              <div className="relative flex items-center justify-center w-full">
                <div className="absolute top-0 left-0 right-0 h-px bg-surface-border" />
              </div>
              {/* Child nodes — each draws their own vertical line up */}
              <div className="flex gap-6 justify-center pt-px">
                {node.children.map((child) => (
                  <div key={child.id} className="flex flex-col items-center">
                    <div className="w-px h-6 bg-surface-border" />
                    <TreeLevel nodes={[child]} depth={depth + 1} />
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
};

const OrgTree: React.FC<OrgTreeProps> = ({ root }) => (
  <div className="overflow-auto pb-8">
    <div className="min-w-max p-8">
      <TreeLevel nodes={[root]} depth={0} />
    </div>
  </div>
);

export default OrgTree;
