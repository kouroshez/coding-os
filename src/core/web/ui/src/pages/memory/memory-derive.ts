// Pure derivation over the /api/patterns rows: the counts the header states,
// the facets the filter bar offers, and the filtered + grouped list the page
// renders. Kept free of React so every rule here is unit-testable.

import type { PatternRow } from './memory-types';
import { UNKNOWN_SOURCE, isArchived, isPromoted, isStat } from './memory-format';

export type SortKey = 'recent' | 'confidence' | 'validated';

export interface MemoryFilters {
  query: string;
  types: string[];
  sources: string[];
  minConfidence: number;
  includeArchived: boolean;
  sort: SortKey;
}

export const EMPTY_FILTERS: MemoryFilters = {
  query: '',
  types: [],
  sources: [],
  minConfidence: 0,
  includeArchived: false,
  sort: 'recent',
};

export function hasActiveFilters(f: MemoryFilters): boolean {
  return (
    f.query.trim() !== '' ||
    f.types.length > 0 ||
    f.sources.length > 0 ||
    f.minConfidence > 0 ||
    f.includeArchived
  );
}

export function toggleValue(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export interface Facet {
  value: string;
  count: number;
}

// Facets are derived from the rows in hand — never a hardcoded vocabulary, so
// a producer that starts emitting a new source/type shows up on its own.
export function facets(rows: PatternRow[], pick: (p: PatternRow) => string): Facet[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const key = pick(row);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
}

export function rowSource(p: PatternRow): string {
  return p.source ?? UNKNOWN_SOURCE;
}

// Facets count the rows the operator can actually select — archived rows only
// once they are opted in — so a chip's number always matches the group it
// produces. Facets deliberately ignore the OTHER facet selections, otherwise
// picking one chip would make the rest disappear.
export function facetPopulation(rows: PatternRow[], includeArchived: boolean): PatternRow[] {
  return includeArchived ? rows : rows.filter((p) => !isArchived(p));
}

export function applyFilters(rows: PatternRow[], f: MemoryFilters): PatternRow[] {
  const needle = f.query.trim().toLowerCase();
  const kept = rows.filter((p) => {
    if (!f.includeArchived && isArchived(p)) return false;
    if (f.types.length > 0 && !f.types.includes(p.memory_type)) return false;
    if (f.sources.length > 0 && !f.sources.includes(rowSource(p))) return false;
    if (p.confidence < f.minConfidence) return false;
    if (needle && !p.pattern.toLowerCase().includes(needle)) return false;
    return true;
  });
  return sortRows(kept, f.sort);
}

const timestamp = (iso: string | null): number => {
  if (!iso) return 0;
  const ms = new Date(iso.includes('T') ? iso : iso.replace(' ', 'T')).getTime();
  return Number.isNaN(ms) ? 0 : ms;
};

export function sortRows(rows: PatternRow[], sort: SortKey): PatternRow[] {
  const out = [...rows];
  if (sort === 'confidence') {
    out.sort((a, b) => b.confidence - a.confidence || b.impact_score - a.impact_score);
  } else if (sort === 'validated') {
    out.sort((a, b) => b.times_validated - a.times_validated || b.confidence - a.confidence);
  } else {
    out.sort((a, b) => timestamp(b.created_at) - timestamp(a.created_at));
  }
  return out;
}

export interface MemoryStats {
  /** Rows in the table, as counted by the producer (may exceed `fetched`). */
  total: number;
  /** Rows this page actually received — the server caps the list. */
  fetched: number;
  truncated: boolean;
  lessons: number;
  stats: number;
  validated: number;
  promoted: number;
  archived: number;
  trusted: number;
  fading: number;
}

export function summarize(rows: PatternRow[], totalCount: number): MemoryStats {
  const live = rows.filter((p) => !isArchived(p));
  return {
    total: totalCount,
    fetched: rows.length,
    truncated: totalCount > rows.length,
    lessons: live.filter((p) => !isStat(p)).length,
    stats: live.filter(isStat).length,
    validated: live.filter((p) => p.times_validated > 0).length,
    promoted: live.filter(isPromoted).length,
    archived: rows.filter(isArchived).length,
    trusted: live.filter((p) => p.tier === 'Trusted').length,
    fading: live.filter((p) => p.tier === 'Fading').length,
  };
}

export interface SourceGroup {
  source: string;
  items: PatternRow[];
}

// Source is the strongest grouping axis on this data — it says where a lesson
// came from, whereas `tier` is "Forming" on effectively every row.
export function groupBySource(rows: PatternRow[]): SourceGroup[] {
  const groups = new Map<string, PatternRow[]>();
  for (const row of rows) {
    const key = rowSource(row);
    const bucket = groups.get(key);
    if (bucket) bucket.push(row);
    else groups.set(key, [row]);
  }
  return [...groups.entries()]
    .map(([source, items]) => ({ source, items }))
    .sort((a, b) => b.items.length - a.items.length || a.source.localeCompare(b.source));
}
