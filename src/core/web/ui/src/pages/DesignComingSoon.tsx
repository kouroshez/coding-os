import { Palette } from 'lucide-react';

import { EmptyState, PageShell } from '@/layout/HubPrimitives';

// Design module — coming-soon surface (TASK-372). The visual design workspace
// (canvas, tokens, component sync) is a roadmap item registered as module id
// `design` in src/core/subsystems.yaml; see ADR-0008. No behaviour is wired yet.
export default function DesignComingSoon() {
  return (
    <PageShell>
      <header className="mb-8">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-[var(--cos-faint)]">
          Roadmap
        </p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-[var(--cos-text)]">Design</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--cos-muted)]">
          A visual design surface for coding-os — a canvas for screens and flows, shared design
          tokens, and two-way component sync with the codebase.
        </p>
      </header>
      <EmptyState icon={<Palette size={28} aria-hidden />} title="Design module — coming soon">
        <p>
          Tracked as module id <code className="text-[var(--cos-text)]">design</code> · see ADR-0008.
          This tab is the module&rsquo;s first surface; nothing is wired yet.
        </p>
      </EmptyState>
    </PageShell>
  );
}
