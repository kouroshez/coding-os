import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { acquireEventSource, pooledConnectionCount } from './shared-event-source';

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static created = 0;

  url: string;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    MockEventSource.created += 1;
  }

  addEventListener() {}
  removeEventListener() {}

  close() {
    this.readyState = 2;
  }
}

describe('acquireEventSource', () => {
  let original: typeof globalThis.EventSource;

  beforeEach(() => {
    original = globalThis.EventSource;
    MockEventSource.created = 0;
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
  });

  afterEach(() => {
    globalThis.EventSource = original;
  });

  it('shares one connection per URL across consumers', () => {
    const a = acquireEventSource('/api/stream/events');
    const b = acquireEventSource('/api/stream/events');
    expect(b.source).toBe(a.source);
    expect(MockEventSource.created).toBe(1);
    a.release();
    b.release();
  });

  it('keys connections by URL — distinct URLs get distinct sources', () => {
    const a = acquireEventSource('/api/stream/events');
    const b = acquireEventSource('/api/hooks/stream');
    expect(b.source).not.toBe(a.source);
    expect(pooledConnectionCount()).toBe(2);
    a.release();
    b.release();
  });

  it('closes only when the last consumer releases', () => {
    const a = acquireEventSource('/api/stream/events');
    const b = acquireEventSource('/api/stream/events');
    a.release();
    expect(a.source.readyState).not.toBe(MockEventSource.CLOSED);
    b.release();
    expect(a.source.readyState).toBe(MockEventSource.CLOSED);
    expect(pooledConnectionCount()).toBe(0);
  });

  it('double-release is a no-op (does not steal a sibling refcount)', () => {
    const a = acquireEventSource('/api/stream/events');
    const b = acquireEventSource('/api/stream/events');
    a.release();
    a.release();
    expect(b.source.readyState).not.toBe(MockEventSource.CLOSED);
    b.release();
    expect(b.source.readyState).toBe(MockEventSource.CLOSED);
  });

  it('replaces a CLOSED pooled source on next acquire', () => {
    const a = acquireEventSource('/api/stream/events');
    a.source.close(); // browser gave up — readyState CLOSED, never reconnects
    const b = acquireEventSource('/api/stream/events');
    expect(b.source).not.toBe(a.source);
    expect(b.source.readyState).not.toBe(MockEventSource.CLOSED);
    a.release();
    b.release();
  });
});
