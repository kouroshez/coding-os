import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { acquireEventSource, pooledConnectionCount } from './shared-event-source';

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static created = 0;
  static instances: MockEventSource[] = [];

  url: string;
  readyState = 0;
  listeners = new Map<string, Set<EventListener>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.created += 1;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: EventListener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)?.add(fn);
  }

  removeEventListener(type: string, fn: EventListener) {
    this.listeners.get(type)?.delete(fn);
  }

  emit(type: string) {
    for (const fn of this.listeners.get(type) ?? []) fn(new Event(type));
  }

  close() {
    this.readyState = 2;
  }
}

describe('acquireEventSource', () => {
  let original: typeof globalThis.EventSource;

  beforeEach(() => {
    original = globalThis.EventSource;
    MockEventSource.created = 0;
    MockEventSource.instances = [];
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

  it('reconnects a CLOSED pooled source in place, keeping its listeners', () => {
    const a = acquireEventSource('/api/stream/events');
    const received: string[] = [];
    a.source.addEventListener('hook', () => received.push('hook'));
    MockEventSource.instances[0].readyState = MockEventSource.CLOSED; // browser gave up
    const b = acquireEventSource('/api/stream/events');
    expect(b.source).toBe(a.source);
    expect(MockEventSource.created).toBe(2);
    expect(b.source.readyState).not.toBe(MockEventSource.CLOSED);
    MockEventSource.instances[1].emit('hook');
    expect(received).toEqual(['hook']);
    a.release();
    b.release();
  });
});

describe('hidden-tab suspension', () => {
  let original: typeof globalThis.EventSource;
  let visibility: DocumentVisibilityState;

  const setVisibility = (state: DocumentVisibilityState) => {
    visibility = state;
    document.dispatchEvent(new Event('visibilitychange'));
  };

  beforeEach(() => {
    vi.useFakeTimers();
    original = globalThis.EventSource;
    MockEventSource.created = 0;
    MockEventSource.instances = [];
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
    visibility = 'visible';
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
  });

  afterEach(() => {
    setVisibility('visible');
    vi.restoreAllMocks();
    vi.useRealTimers();
    globalThis.EventSource = original;
  });

  it('closes the connection after the grace period and keeps listeners', () => {
    const shared = acquireEventSource('/api/hooks/stream');
    shared.source.addEventListener('hook', () => undefined);
    setVisibility('hidden');
    expect(MockEventSource.instances[0].readyState).not.toBe(MockEventSource.CLOSED);
    vi.advanceTimersByTime(10_000);
    expect(MockEventSource.instances[0].readyState).toBe(MockEventSource.CLOSED);
    expect(shared.source.readyState).toBe(MockEventSource.CONNECTING);
    shared.release();
  });

  it('a quick tab switch inside the grace period does not reconnect', () => {
    const shared = acquireEventSource('/api/hooks/stream');
    setVisibility('hidden');
    vi.advanceTimersByTime(3_000);
    setVisibility('visible');
    vi.advanceTimersByTime(20_000);
    expect(MockEventSource.created).toBe(1);
    expect(MockEventSource.instances[0].readyState).not.toBe(MockEventSource.CLOSED);
    shared.release();
  });

  it('reopens on visible and delivers events to the kept listeners', () => {
    const shared = acquireEventSource('/api/hooks/stream');
    const received: string[] = [];
    shared.source.addEventListener('open', () => received.push('open'));
    shared.source.addEventListener('hook', () => received.push('hook'));
    setVisibility('hidden');
    vi.advanceTimersByTime(10_000);
    setVisibility('visible');
    expect(MockEventSource.created).toBe(2);
    const reopened = MockEventSource.instances[1];
    expect(reopened.url).toBe('/api/hooks/stream');
    reopened.emit('open');
    reopened.emit('hook');
    expect(received).toEqual(['open', 'hook']);
    shared.release();
    expect(reopened.readyState).toBe(MockEventSource.CLOSED);
  });

  it('a removed listener is not moved onto the reconnection', () => {
    const shared = acquireEventSource('/api/hooks/stream');
    const received: string[] = [];
    const fn = () => received.push('hook');
    shared.source.addEventListener('hook', fn);
    shared.source.removeEventListener('hook', fn);
    setVisibility('hidden');
    vi.advanceTimersByTime(10_000);
    setVisibility('visible');
    MockEventSource.instances[1].emit('hook');
    expect(received).toEqual([]);
    shared.release();
  });
});
