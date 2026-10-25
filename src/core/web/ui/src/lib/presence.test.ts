import { describe, expect, it } from 'vitest';

import { agentStatus, chatHref, gateMeta, modelLabel } from './presence';

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

  it('does not swallow a date suffix as the minor version', () => {
    expect(modelLabel('claude-sonnet-5-20260101')).toBe('Sonnet 5');
    expect(modelLabel('claude-opus-4-8[1m]')).toBe('Opus 4.8 · 1M');
  });

  it('falls back to the raw id for unknown shapes, and a friendly label for null', () => {
    expect(modelLabel('gpt-5')).toBe('gpt-5');
    expect(modelLabel(null)).toBe('Unknown runtime');
  });
});

describe('gateMeta', () => {
  it('parses level + dimensions', () => {
    expect(gateMeta('COMPLEX 6')).toEqual({ level: 'Complex', dims: '6', color: '#b45309' });
  });

  it('handles a bare level with no dimensions', () => {
    expect(gateMeta('CLEAR')).toEqual({ level: 'Clear', dims: null, color: '#15803d' });
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

describe('chatHref', () => {
  it('builds a project-scoped chat link from the agent slug', () => {
    expect(chatHref('my-app', null, 'SDK-1')).toBe('/p/my-app/workspace/chat/SDK-1');
  });

  it('falls back to the URL slug when the agent carries none', () => {
    expect(chatHref(null, 'url-proj', 'sess-2')).toBe('/p/url-proj/workspace/chat/sess-2');
  });

  it('prefers the agent slug over the URL slug', () => {
    expect(chatHref('owner', 'other', 'id')).toBe('/p/owner/workspace/chat/id');
  });

  it('returns null without an owner or an id', () => {
    expect(chatHref(null, null, 'id')).toBeNull();
    expect(chatHref('owner', null, null)).toBeNull();
  });

  it('encodes the slug and the id', () => {
    expect(chatHref('a b', null, 'x/y')).toBe('/p/a%20b/workspace/chat/x%2Fy');
  });
});
