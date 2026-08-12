import { describe, it, expect } from 'vitest';

import { confidenceBand, isArchived, isPromoted, sourceCopy, splitLesson, tierStyle } from './memory-format';
import type { PatternRow } from './memory-types';

const row = (patch: Partial<PatternRow> = {}): PatternRow => ({
  id: 1,
  pattern: 'x',
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

// Regression guard for the audit finding: splitLesson previously matched ONLY
// the "Recurring …" format, silently dropping the action line from revert/fix
// lessons (50% of live lessons). It must split every producer format on " → ".
describe('splitLesson', () => {
  it('splits the "Recurring …" format and strips the prefix', () => {
    const r = splitLesson(
      'Recurring completion gap (2 occurrences): left a task open → close it before ending',
    );
    expect(r.situation).toBe('left a task open');
    expect(r.action).toBe('close it before ending');
  });

  it('splits the "Reverted before:" format (the regressed case)', () => {
    const r = splitLesson(
      'Reverted before: switch GraphPage back to 2D → reconsider before re-introducing this change.',
    );
    expect(r.situation).toBe('Reverted before: switch GraphPage back to 2D');
    expect(r.action).toBe('reconsider before re-introducing this change.');
  });

  it('splits the "Fixed repeatedly …" format and strips the prefix', () => {
    const r = splitLesson(
      'Fixed repeatedly (3 occurrences): null user crash → address the root cause, not the symptom.',
    );
    expect(r.situation).toBe('null user crash');
    expect(r.action).toBe('address the root cause, not the symptom.');
  });

  it('returns no action for arrow-less text', () => {
    const r = splitLesson('[Breakthrough] FTS5 external-content corrupts on rebuild');
    expect(r.action).toBeNull();
    expect(r.situation).toBe('[Breakthrough] FTS5 external-content corrupts on rebuild');
  });

  it('splits at the LAST arrow when several are present', () => {
    const r = splitLesson('a → b → c');
    expect(r.situation).toBe('a → b');
    expect(r.action).toBe('c');
  });

  it('falls back to the un-stripped left when the prefix consumes everything', () => {
    const r = splitLesson('Recurring completion gap (1 occurrence): → act now');
    expect(r.action).toBe('act now');
    expect(r.situation).toBe('Recurring completion gap (1 occurrence):'); // not empty
  });

  it('handles empty input', () => {
    const r = splitLesson('');
    expect(r.situation).toBe('');
    expect(r.action).toBeNull();
  });
});

describe('confidenceBand', () => {
  it('labels the number instead of colouring a bare bar', () => {
    expect(confidenceBand(0.95).label).toBe('strong');
    expect(confidenceBand(0.6).label).toBe('moderate');
    expect(confidenceBand(0.29).label).toBe('weak');
  });
});

// Every live row is tier "Forming"; a badge on all of them carries no signal,
// so only Trusted/Fading render one.
describe('tierStyle', () => {
  it('returns no style for Forming', () => {
    expect(tierStyle('Forming')).toBeNull();
  });
  it('styles Trusted and Fading', () => {
    expect(tierStyle('Trusted')).not.toBeNull();
    expect(tierStyle('Fading')).not.toBeNull();
  });
});

describe('sourceCopy', () => {
  it('explains every producer source in one phrase', () => {
    for (const source of ['friction', 'breakthrough', 'learn_extract', 'commit']) {
      expect(sourceCopy(source).blurb.length).toBeGreaterThan(10);
    }
  });
  it('falls through to the raw value for an unknown source', () => {
    expect(sourceCopy('brand_new').label).toBe('brand_new');
  });
  it('handles a null source', () => {
    expect(sourceCopy(null).label).toBe('No source recorded');
  });
});

describe('promotion state', () => {
  it('treats promoted_to="archived" as archived, not promoted', () => {
    expect(isArchived(row({ promoted_to: 'archived' }))).toBe(true);
    expect(isPromoted(row({ promoted_to: 'archived' }))).toBe(false);
  });
  it('treats any other promoted_to as promoted', () => {
    expect(isPromoted(row({ promoted_to: 'feedback:feedback_pattern_22.md' }))).toBe(true);
  });
});
