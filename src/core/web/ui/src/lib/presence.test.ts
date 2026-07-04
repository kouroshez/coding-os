import { describe, expect, it } from 'vitest';

import { agentStatus, cognitionHref, gateMeta, modelLabel } from './presence';

describe('modelLabel', () => {
  it('humanizes a claude model id with a context window', () => {
    expect(modelLabel('claude-opus-4-8[1m]')).toBe('Opus 4.8 · 1M');
  });

  it('handles a model id without a context bracket', () => {
    expect(modelLabel('claude-sonnet-4-6')).toBe('Sonnet 4.6');
  });

  it('handles a single-integer version id (Sonnet 5 / Fable 5)', () => {
    expect(modelLabel('claude-sonnet-5')).toBe('Sonnet 5');
    expect(modelLabel('claude-fable-5')).toBe('Fable 5');
    expect(modelLabel('claude-haiku-4-5-20251001')).toBe('Haiku 4.5');
  });

  it('falls back to the raw id for unknown shapes, and a friendly label for null', () => {
    expect(modelLabel('gpt-5')).toBe('gpt-5');
    expect(modelLabel(null)).toBe('Unknown runtime');
  });
});

describe('gateMeta', () => {
  it('parses level + dimensions', () => {
    expect(gateMeta('COMPLEX 6')).toEqual({ level: 'Complex', dims: '6', color: '#f59e0b' });
  });

  it('handles a bare level with no dimensions', () => {
    expect(gateMeta('CLEAR')).toEqual({ level: 'Clear', dims: null, color: '#16a34a' });
  });

  it('returns null when unset', () => {
    expect(gateMeta(null)).toBeNull();
    expect(gateMeta('')).toBeNull();
  });
});

describe('agentStatus', () => {
  it('maps known states to a label + pulse flag', () => {
    expect(agentStatus('active')).toMatchObject({ label: 'Active', pulse: true });
    expect(agentStatus('present')).toMatchObject({ label: 'Idle', pulse: false });
  });

  it('falls back for unknown / missing states', () => {
    expect(agentStatus('weird').label).toBe('Weird');
    expect(agentStatus(null).label).toBe('Offline');
  });
});

describe('cognitionHref', () => {
  it('builds a project-scoped link from the agent slug', () => {
    expect(cognitionHref('my-app', null, 'SDK-1', 'chat')).toBe('/p/my-app/cognition/SDK-1?view=chat');
  });

  it('falls back to the URL slug when the agent carries none', () => {
    expect(cognitionHref(null, 'url-proj', 'sess-2', 'trace')).toBe('/p/url-proj/cognition/sess-2?view=trace');
  });

  it('prefers the agent slug over the URL slug', () => {
    expect(cognitionHref('owner', 'other', 'id', 'chat')).toBe('/p/owner/cognition/id?view=chat');
  });

  it('returns null (never the unscoped picker) when no owner or id resolves', () => {
    expect(cognitionHref(null, null, 'id', 'chat')).toBeNull();
    expect(cognitionHref('owner', null, null, 'chat')).toBeNull();
  });

  it('encodes the slug and id', () => {
    expect(cognitionHref('a b', null, 'x/y', 'chat')).toBe('/p/a%20b/cognition/x%2Fy?view=chat');
  });
});
