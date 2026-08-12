import { useEffect, useId, useState } from 'react';
import { CfgButton, Chip } from '@/features/config/shared';
import type { Facet, MemoryFilters, SortKey } from './memory-derive';
import { hasActiveFilters, toggleValue } from './memory-derive';
import { sourceCopy, typeLabel } from './memory-format';

const CONFIDENCE_FLOORS: { value: number; label: string }[] = [
  { value: 0, label: 'Any confidence' },
  { value: 0.4, label: 'At least 40%' },
  { value: 0.6, label: 'At least 60%' },
  { value: 0.8, label: 'At least 80%' },
];

const SORTS: { value: SortKey; label: string }[] = [
  { value: 'recent', label: 'Newest first' },
  { value: 'confidence', label: 'Highest confidence' },
  { value: 'validated', label: 'Most validated' },
];

const selectClass =
  'rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1 text-[12px] text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]';

function FacetGroup({
  legend,
  facets,
  selected,
  labelFor,
  onToggle,
}: {
  legend: string;
  facets: Facet[];
  selected: string[];
  labelFor: (value: string) => string;
  onToggle: (value: string) => void;
}) {
  if (facets.length === 0) return null;
  return (
    <fieldset className="min-w-0 border-0 p-0">
      <legend className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--cos-muted)]">
        {legend}
      </legend>
      <div className="flex flex-wrap gap-1.5">
        {facets.map((f) => (
          <Chip
            key={f.value}
            active={selected.includes(f.value)}
            onClick={() => onToggle(f.value)}
            ariaLabel={`${legend}: ${labelFor(f.value)} — ${f.count} row${f.count === 1 ? '' : 's'}`}
          >
            {labelFor(f.value)} <span className="tabular-nums opacity-70">{f.count}</span>
          </Chip>
        ))}
      </div>
    </fieldset>
  );
}

export function MemoryFilterBar({
  filters,
  typeFacets,
  sourceFacets,
  archivedCount,
  shown,
  total,
  onPatch,
  onClear,
}: {
  filters: MemoryFilters;
  typeFacets: Facet[];
  sourceFacets: Facet[];
  archivedCount: number;
  shown: number;
  total: number;
  onPatch: (patch: Partial<MemoryFilters>) => void;
  onClear: () => void;
}) {
  const searchId = useId();
  const confidenceId = useId();
  const sortId = useId();
  const [draft, setDraft] = useState(filters.query);

  // Debounced hand-off: typing stays local, the (re-)filter runs once the
  // operator pauses. 111 rows filter instantly; the debounce keeps the
  // grouped list from re-rendering on every keystroke.
  useEffect(() => {
    if (draft === filters.query) return;
    const timer = setTimeout(() => onPatch({ query: draft }), 220);
    return () => clearTimeout(timer);
  }, [draft, filters.query, onPatch]);

  return (
    <section
      aria-label="Search and filter lessons"
      className="mb-5 rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-4 py-3"
    >
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-[16rem] flex-1">
          <label
            htmlFor={searchId}
            className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-[var(--cos-muted)]"
          >
            Search lesson text
          </label>
          <input
            id={searchId}
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. commit, branch, pytest"
            className="w-full rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-1.5 text-[13px] text-[var(--cos-text)] placeholder:text-[var(--cos-faint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
          />
        </div>
        <div>
          <label
            htmlFor={confidenceId}
            className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-[var(--cos-muted)]"
          >
            Confidence floor
          </label>
          <select
            id={confidenceId}
            value={filters.minConfidence}
            onChange={(e) => onPatch({ minConfidence: Number(e.target.value) })}
            className={selectClass}
          >
            {CONFIDENCE_FLOORS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor={sortId}
            className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-[var(--cos-muted)]"
          >
            Sort
          </label>
          <select
            id={sortId}
            value={filters.sort}
            onChange={(e) => onPatch({ sort: e.target.value as SortKey })}
            className={selectClass}
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-3">
        <FacetGroup
          legend="Type"
          facets={typeFacets}
          selected={filters.types}
          labelFor={typeLabel}
          onToggle={(v) => onPatch({ types: toggleValue(filters.types, v) })}
        />
        <FacetGroup
          legend="Source"
          facets={sourceFacets}
          selected={filters.sources}
          labelFor={(v) => sourceCopy(v === 'unknown' ? null : v).label}
          onToggle={(v) => onPatch({ sources: toggleValue(filters.sources, v) })}
        />
        {archivedCount > 0 && (
          <fieldset className="min-w-0 border-0 p-0">
            <legend className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--cos-muted)]">
              Archived
            </legend>
            <Chip
              active={filters.includeArchived}
              onClick={() => onPatch({ includeArchived: !filters.includeArchived })}
              ariaLabel={`Include ${archivedCount} archived rows`}
            >
              Include archived <span className="tabular-nums opacity-70">{archivedCount}</span>
            </Chip>
          </fieldset>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--cos-border)] pt-2.5">
        <p role="status" className="text-[12px] text-[var(--cos-muted)]">
          Showing <span className="tabular-nums text-[var(--cos-text)]">{shown}</span> of{' '}
          <span className="tabular-nums">{total}</span> rows
        </p>
        {hasActiveFilters(filters) && (
          <CfgButton
            onClick={() => {
              setDraft('');
              onClear();
            }}
          >
            Clear filters
          </CfgButton>
        )}
      </div>
    </section>
  );
}
