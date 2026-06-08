import { describe, expect, it } from 'vitest';

import { shortTime } from './LogsPage';

describe('LogsPage shortTime — viewer-local timezone (TASK-262)', () => {
  it('converts a UTC ISO timestamp to the viewer local clock, not a raw slice', () => {
    const iso = '2026-06-08T16:54:16Z';
    const expectedLocal = new Date(iso).toLocaleTimeString(undefined, { hour12: false });
    expect(shortTime(iso)).toBe(expectedLocal);
    // In ANY non-UTC timezone the rendered time must differ from the raw UTC slice
    // (the old bug: an EDT viewer saw 16:54:16 instead of 12:54:16).
    if (new Date(iso).getTimezoneOffset() !== 0) {
      expect(shortTime(iso)).not.toBe('16:54:16');
    }
  });

  it('falls back to the raw slice for an unparseable timestamp', () => {
    const junk = 'ABCDEFGHIJK12:00:00Z'; // len 20, not a date → keep legacy slice(11,19)
    expect(shortTime(junk)).toBe(junk.slice(11, 19));
  });

  it('returns empty input unchanged', () => {
    expect(shortTime('')).toBe('');
  });
});
