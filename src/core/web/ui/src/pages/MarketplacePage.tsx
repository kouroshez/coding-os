import { Store } from 'lucide-react';

import { EmptyState, PageHeader, PageShell, SkeletonGrid } from '@/layout/HubPrimitives';

// Marketplace — the public catalog surface for the Extension Manager
// (docs/engineering/extension-manager.md). Coming-soon: a skeleton + framing
// only, no data wired. Skills + MCP install/upload land with the EM epic;
// hooks/rules/commands stay read-only DNA (never installable from the Hub).
export default function MarketplacePage() {
  return (
    <PageShell>
      <PageHeader
        eyebrow="Roadmap · Extension Manager"
        title="Marketplace"
        subtitle="A community package manager for coding-os — browse and install skills and MCP servers others have published, or share your own. Every install passes the Extension Manager's fail-closed trust gate (scan → approve → enable)."
      />
      <div aria-hidden className="pointer-events-none mb-8 opacity-40">
        <SkeletonGrid count={6} height={132} />
      </div>
      <EmptyState icon={<Store size={28} aria-hidden />} title="Marketplace — coming soon">
        <p>
          Publishing and installing community skills and MCP servers is designed in{' '}
          <code className="text-[var(--cos-text)]">docs/engineering/extension-manager.md</code>. Nothing is
          wired yet — skills and MCP arrive first; hooks, rules, and commands stay read-only DNA.
        </p>
      </EmptyState>
    </PageShell>
  );
}
