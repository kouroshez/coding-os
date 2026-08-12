import { describe, it, expect } from 'vitest';

import {
  EMPTY_FILTERS,
  applyFilters,
  facetPopulation,
  facets,
  groupBySource,
  hasActiveFilters,
  rowSource,
  sortRows,
  summarize,
  toggleValue,
} from './memory-derive';
import type { PatternRow } from './memory-types';

const row = (patch: Partial<PatternRow> = {}): PatternRow => ({
  id: 1,
  pattern: 'a lesson',
  memory_type: 'lesson',
  domain: null,
  source: 'friction',
  confidence: 0.6,
  decay_rate: 0.01,
  impact_score: 1,
  times_validated: 0,
  times_violated: 0,
  access_count: 0,
  trust_tier: 'volatile',
  tier: 'Forming',
  provenance: 'extracted_from_observation',
  promoted_to: null,
  evidence_json: null,
  last_validated: null,
  last_accessed_at: null,
  created_at: '2026-08-01 10:00:00',
  ...patch,
});

const corpus: PatternRow[] = [
  row({ id: 1, pattern: 'never bare git commit', source: 'friction', confidence: 0.9 }),
  row({ id: 2, pattern: 'branch guard blocks checkout', source: 'friction', confidence: 0.3 }),
  row({ id: 3, pattern: 'FTS5 rebuild corrupts', source: 'breakthrough', memory_type: 'error' }),
  row({ id: 4, pattern: 'INFRA succeeds at 95%', source: 'learn_extract', memory_type: 'stat' }),
  row({ id: 5, pattern: 'archived thing', source: 'friction', promoted_to: 'archived' }),
  row({ id: 6, pattern: 'unattributed', source: null }),
];

describe('facets', () => {
  it('derives values from the data, never a hardcoded list', () => {
    expect(facets(corpus, (p) => p.memory_type)).toEqual([
      { value: 'lesson', count: 4 },
      { value: 'error', count: 1 },
      { value: 'stat', count: 1 },
    ]);
  });

  it('buckets a null source under a stable key so it is filterable', () => {
    const bySource = facets(corpus, rowSource);
    expect(bySource.find((f) => f.value === 'unknown')?.count).toBe(1);
  });

  // A chip that counts rows the list then hides is the drift the old page had
  // between its header count and its rendered groups.
  it('counts only the rows a chip would actually surface', () => {
    const visible = facets(facetPopulation(corpus, false), rowSource);
    expect(visible.find((f) => f.value === 'friction')?.count).toBe(2);
    const withArchived = facets(facetPopulation(corpus, true), rowSource);
    expect(withArchived.find((f) => f.value === 'friction')?.count).toBe(3);
  });
});

describe('applyFilters', () => {
  it('hides archived rows unless explicitly included', () => {
    const ids = applyFilters(corpus, EMPTY_FILTERS).map((p) => p.id);
    expect(ids).not.toContain(5);
    expect(applyFilters(corpus, { ...EMPTY_FILTERS, includeArchived: true }).map((p) => p.id)).toContain(5);
  });

  it('matches the lesson text case-insensitively', () => {
    const out = applyFilters(corpus, { ...EMPTY_FILTERS, query: 'GIT COMMIT' });
    expect(out.map((p) => p.id)).toEqual([1]);
  });

  it('filters by memory_type and by source', () => {
    expect(applyFilters(corpus, { ...EMPTY_FILTERS, types: ['stat'] }).map((p) => p.id)).toEqual([4]);
    expect(
      applyFilters(corpus, { ...EMPTY_FILTERS, sources: ['breakthrough'] }).map((p) => p.id),
    ).toEqual([3]);
  });

  it('applies the confidence floor', () => {
    expect(applyFilters(corpus, { ...EMPTY_FILTERS, minConfidence: 0.8 }).map((p) => p.id)).toEqual([1]);
  });

  it('combines filters conjunctively', () => {
    const out = applyFilters(corpus, {
      ...EMPTY_FILTERS,
      sources: ['friction'],
      minConfidence: 0.5,
      query: 'commit',
    });
    expect(out.map((p) => p.id)).toEqual([1]);
  });
});

describe('sortRows', () => {
  it('sorts by confidence and by validation count', () => {
    const rows = [row({ id: 1, confidence: 0.2, times_validated: 5 }), row({ id: 2, confidence: 0.9 })];
    expect(sortRows(rows, 'confidence').map((p) => p.id)).toEqual([2, 1]);
    expect(sortRows(rows, 'validated').map((p) => p.id)).toEqual([1, 2]);
  });

  it('sorts newest first by created_at', () => {
    const rows = [
      row({ id: 1, created_at: '2026-01-01 00:00:00' }),
      row({ id: 2, created_at: '2026-08-01 00:00:00' }),
    ];
    expect(sortRows(rows, 'recent').map((p) => p.id)).toEqual([2, 1]);
  });
});

// The header's whole job is stating these numbers honestly — including the
// server-side truncation the old page never surfaced.
describe('summarize', () => {
  it('counts lessons, stats and archived rows separately', () => {
    const s = summarize(corpus, corpus.length);
    expect(s.lessons).toBe(4);
    expect(s.stats).toBe(1);
    expect(s.archived).toBe(1);
    expect(s.truncated).toBe(false);
  });

  it('flags truncation when the producer holds more rows than were fetched', () => {
    expect(summarize(corpus, 111).truncated).toBe(true);
    expect(summarize(corpus, 111).total).toBe(111);
  });

  it('counts validated / promoted / trusted from the real fields', () => {
    const s = summarize(
      [
        row({ id: 1, times_validated: 3, tier: 'Trusted', confidence: 0.8 }),
        row({ id: 2, promoted_to: 'feedback:x.md' }),
        row({ id: 3, tier: 'Fading', times_violated: 2 }),
      ],
      3,
    );
    expect(s.validated).toBe(1);
    expect(s.promoted).toBe(1);
    expect(s.trusted).toBe(1);
    expect(s.fading).toBe(1);
  });
});

describe('groupBySource', () => {
  it('groups by source, largest group first', () => {
    const groups = groupBySource(corpus);
    expect(groups[0]).toMatchObject({ source: 'friction' });
    expect(groups[0].items).toHaveLength(3);
    expect(groups.map((g) => g.source)).toContain('unknown');
  });
});

describe('filter helpers', () => {
  it('toggleValue adds then removes', () => {
    expect(toggleValue([], 'a')).toEqual(['a']);
    expect(toggleValue(['a'], 'a')).toEqual([]);
  });

  it('hasActiveFilters ignores sort but sees every real filter', () => {
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, sort: 'confidence' })).toBe(false);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, query: 'x' })).toBe(true);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, minConfidence: 0.4 })).toBe(true);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, includeArchived: true })).toBe(true);
  });
});
