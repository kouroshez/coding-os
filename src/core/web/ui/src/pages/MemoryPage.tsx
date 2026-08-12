import { useCallback, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { Banner, EmptyState, Icon, PageHeader, PageShell, SkeletonGrid, StatusPill } from '@/layout/HubPrimitives';
import type { PatternsData, RoiData } from './memory/memory-types';
import {
  EMPTY_FILTERS,
  applyFilters,
  facetPopulation,
  facets,
  groupBySource,
  hasActiveFilters,
  rowSource,
  summarize,
  type MemoryFilters,
} from './memory/memory-derive';
import { MemoryOverview } from './memory/MemoryOverview';
import { MemoryLoopPanel } from './memory/MemoryLoopPanel';
import { MemoryFilterBar } from './memory/MemoryFilterBar';
import { MemoryList } from './memory/MemoryList';

// /api/patterns caps `limit` at 500 (routes/patterns.py). The default of 100
// silently dropped the lowest-confidence rows — including every `error` row on
// this project — while the page still reported a total. Ask for the cap and
// surface `total_count` when even that truncates.
const PATTERN_LIMIT = 500;

export default function MemoryPage() {
  const { slug } = useParams<{ slug?: string }>();
  const [filters, setFilters] = useState<MemoryFilters>(EMPTY_FILTERS);

  const patterns = useApiGet<PatternsData>(['patterns', PATTERN_LIMIT], '/api/patterns', {
    limit: PATTERN_LIMIT,
  });
  const roi = useApiGet<RoiData>(['patterns-roi'], '/api/patterns/roi');

  const rows = useMemo(() => patterns.data?.patterns ?? [], [patterns.data]);
  const stats = useMemo(
    () => summarize(rows, patterns.data?.total_count ?? rows.length),
    [rows, patterns.data],
  );
  const population = useMemo(
    () => facetPopulation(rows, filters.includeArchived),
    [rows, filters.includeArchived],
  );
  const typeFacets = useMemo(() => facets(population, (p) => p.memory_type), [population]);
  const sourceFacets = useMemo(() => facets(population, rowSource), [population]);
  const visible = useMemo(() => applyFilters(rows, filters), [rows, filters]);
  const groups = useMemo(() => groupBySource(visible), [visible]);

  const patchFilters = useCallback((patch: Partial<MemoryFilters>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
  }, []);
  const clearFilters = useCallback(() => setFilters(EMPTY_FILTERS), []);

  const empty = !patterns.isLoading && !patterns.error && rows.length === 0;

  return (
    <PageShell>
      <PageHeader
        eyebrow={<StatusPill label="learning · agent memory" />}
        title="Agent Memory"
        subtitle="Every lesson the agent has distilled from its own friction, and how far each one has actually travelled. A lesson only becomes durable once sessions confirm it."
      />

      {patterns.isLoading && <SkeletonGrid count={3} height={96} />}

      {patterns.error && (
        <Banner kind="error">Failed to load patterns: {patterns.error.message}</Banner>
      )}

      {empty && (
        <EmptyState icon={<Icon name="cognition" size={28} />} title="No lessons yet">
          The agent has not hit enough repeated friction to distil one. Lessons appear when the
          learning loop runs — nightly, every 10th task, or on demand below.
        </EmptyState>
      )}

      {!patterns.isLoading && !patterns.error && rows.length > 0 && (
        <>
          <MemoryOverview
            stats={stats}
            roi={roi.data ?? null}
            roiLoading={roi.isLoading}
            roiFailed={!!roi.error}
          />
          <MemoryLoopPanel slug={slug} />
          <MemoryFilterBar
            filters={filters}
            typeFacets={typeFacets}
            sourceFacets={sourceFacets}
            archivedCount={stats.archived}
            shown={visible.length}
            total={rows.length}
            onPatch={patchFilters}
            onClear={clearFilters}
          />
          <MemoryList
            groups={groups}
            filtered={hasActiveFilters(filters)}
            onClear={clearFilters}
          />
        </>
      )}

      {empty && <MemoryLoopPanel slug={slug} />}
    </PageShell>
  );
}
