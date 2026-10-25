import { useCallback, useMemo, useState } from 'react';
import { Brain, Search } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { Banner, EmptyState, PageHeader, PageShell, SkeletonGrid } from '@/layout/HubPrimitives';
import { BudgetCard, HealthCard, TypeFilter } from './memory/MemorySidebar';
import { MemoryGroupSection } from './memory/MemoryGroups';
import {
  groupAnchor,
  groupMemory,
  typeCounts,
  unindexedMemories,
  type MemoryPayload,
} from './memory/memory-view';

function scrollToId(id: string) {
  requestAnimationFrame(() =>
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
  );
}

export default function MemoryPage() {
  const { data, isLoading, error } = useApiGet<MemoryPayload>(['memory'], '/api/memory');
  const [query, setQuery] = useState('');
  const [type, setType] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  const groups = useMemo(() => (data ? groupMemory(data, query, type) : []), [data, query, type]);
  const memories = useMemo(() => data?.memories ?? [], [data]);
  const unindexed = useMemo(() => (data ? unindexedMemories(data) : []), [data]);

  const toggle = useCallback((slug: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }, []);

  const openLink = useCallback((slug: string) => {
    setQuery('');
    setType(null);
    setExpanded((prev) => new Set(prev).add(slug));
    scrollToId(`memory-${slug}`);
  }, []);

  const jump = useCallback((name: string) => {
    setQuery('');
    setType(null);
    scrollToId(groupAnchor(name));
  }, []);

  if (isLoading) {
    return (
      <PageShell>
        <SkeletonGrid count={3} height={120} />
      </PageShell>
    );
  }
  if (error) {
    return (
      <PageShell>
        <Banner kind="error">Could not read the memory folder: {error.message}</Banner>
      </PageShell>
    );
  }
  if (!data?.present) {
    return (
      <PageShell>
        <EmptyState icon={<Brain size={28} aria-hidden />} title="No agent memory in this project">
          Memory lives as markdown in{' '}
          <code className="font-mono">{data?.dir ?? '.agents/memory'}</code>, indexed by{' '}
          <code className="font-mono">MEMORY.md</code>. Agents create it the first time they save a
          memory.
        </EmptyState>
      </PageShell>
    );
  }

  const filtering = query.trim() !== '' || type !== null;
  const shown = groups.reduce((sum, g) => sum + g.rows.filter((r) => !r.subIndex).length, 0);

  return (
    <PageShell>
      <PageHeader
        eyebrow={<span>Agent memory · {data.dir}</span>}
        title="Memory"
        subtitle="What agents carry between sessions, read straight from the files every agent loads. Edit them in the repo; this view only reads."
        right={
          <div className="text-end">
            <div className="text-3xl font-semibold tabular-nums text-[var(--cos-text)]">
              {memories.length}
            </div>
            <div className="text-[11px] text-[var(--cos-muted)]">
              memories · {(data.indexes?.length ?? 1) - 1} sub-index
              {(data.indexes?.length ?? 1) - 1 === 1 ? '' : 'es'}
            </div>
          </div>
        }
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          {data.lint && <HealthCard lint={data.lint} />}
          {data.budget && <BudgetCard budget={data.budget} />}
          <TypeFilter
            counts={typeCounts(memories)}
            total={memories.length}
            selected={type}
            onSelect={setType}
          />
        </aside>
        <div className="min-w-0 space-y-6">
          <label className="relative block">
            <span className="sr-only">Filter memories</span>
            <Search
              size={14}
              aria-hidden
              className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--cos-muted)]"
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by title, rule or content…"
              className="w-full rounded-xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/60 py-2 pe-3 ps-9 text-sm text-[var(--cos-text)] placeholder:text-[var(--cos-muted)] focus:border-[var(--accent)] focus:outline-none"
            />
          </label>
          {filtering && (
            <p className="px-1 text-xs text-[var(--cos-muted)]" aria-live="polite">
              {shown} of {memories.length} match
            </p>
          )}
          {groups.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-[var(--cos-border)] px-4 py-10 text-center text-sm text-[var(--cos-muted)]">
              No memory matches this filter.
            </p>
          ) : (
            groups.map((group) => (
              <MemoryGroupSection
                key={group.index.name}
                group={group}
                isRoot={group.index.name === data.indexes?.[0]?.name}
                expanded={expanded}
                onToggle={toggle}
                onOpenLink={openLink}
                onJump={jump}
              />
            ))
          )}
          {!filtering && unindexed.length > 0 && (
            <section className="rounded-2xl border border-[var(--cos-err)]/50 bg-[var(--cos-err-tint)] p-4">
              <h3 className="text-sm font-semibold text-[var(--cos-err)]">
                Not linked from any index
              </h3>
              <p className="mt-1 text-xs text-[var(--cos-muted)]">
                No session finds these until a line in MEMORY.md or a sub-index points at them.
              </p>
              <ul className="mt-2 space-y-1 font-mono text-xs text-[var(--cos-text)]">
                {unindexed.map((m) => (
                  <li key={m.slug}>{m.slug}.md</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </PageShell>
  );
}
