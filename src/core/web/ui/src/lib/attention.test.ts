import { describe, expect, it } from 'vitest';
import { formatTabTitle, summarizeStreamEvent } from './attention';

describe('formatTabTitle (TASK-252)', () => {
  it('shows the bare base at zero unread', () => {
    expect(formatTabTitle(0)).toBe('Coding OS Hub');
  });
  it('prefixes the unread count', () => {
    expect(formatTabTitle(3, 'Coding OS Hub')).toBe('(3) Coding OS Hub');
  });
});

describe('summarizeStreamEvent (TASK-252)', () => {
  it('phrases a completed dispatch', () => {
    expect(summarizeStreamEvent('dispatch-completed', { formula_id: 'reviewer', status: 'ok' })).toBe(
      'reviewer finished',
    );
  });
  it('surfaces a non-ok status', () => {
    expect(
      summarizeStreamEvent('dispatch-completed', { formula_id: 'impl', status: 'timeout' }),
    ).toBe('impl timeout');
  });
  it('phrases blocked + needs-input', () => {
    expect(summarizeStreamEvent('agent-blocked', { reason: 'no doc anchor' })).toBe(
      'Agent blocked: no doc anchor',
    );
    expect(summarizeStreamEvent('needs-input', {})).toBe('Agent needs your input');
  });
  it('falls back to the raw type for unknown events', () => {
    expect(summarizeStreamEvent('weird', null)).toBe('weird');
  });
});
