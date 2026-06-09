import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { reportClientError } from './client-logger';

describe('client-logger', () => {
  const realFetch = globalThis.fetch;
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
  });

  function mockFetch() {
    const fetchMock = vi.fn((_url: RequestInfo | URL, _init?: RequestInit) =>
      Promise.resolve({ ok: true } as Response),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    return fetchMock;
  }

  function bodyOf(init: RequestInit | undefined): Record<string, unknown> {
    return JSON.parse((init?.body as string) ?? '{}');
  }

  it('beacons the error to /api/logs/client with the message + level', () => {
    const fetchMock = mockFetch();
    reportClientError('boom', { a: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/logs/client');
    const body = bodyOf(fetchMock.mock.calls[0][1]);
    expect(body.message).toBe('boom');
    expect(body.level).toBe('error');
    expect(body.context).toEqual({ a: 1 });
  });

  it('never throws when fetch rejects (logging must not break the app)', () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('network'))) as unknown as typeof fetch;
    expect(() => reportClientError('x')).not.toThrow();
  });

  it('serializes an Error context with name/message/stack', () => {
    const fetchMock = mockFetch();
    reportClientError('failed', new Error('the cause'));
    const ctx = bodyOf(fetchMock.mock.calls[0][1]).context as {
      name?: string;
      message?: string;
      stack?: string;
    };
    expect(ctx.message).toBe('the cause');
    expect(ctx.name).toBe('Error');
    expect(ctx).toHaveProperty('stack');
  });

  it('respects the level argument', () => {
    const fetchMock = mockFetch();
    reportClientError('heads up', undefined, 'warn');
    expect(bodyOf(fetchMock.mock.calls[0][1]).level).toBe('warn');
  });
});
