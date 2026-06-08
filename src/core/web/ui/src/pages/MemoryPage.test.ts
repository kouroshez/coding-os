import { describe, it, expect } from 'vitest';

import { splitLesson } from './MemoryPage';

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
});
