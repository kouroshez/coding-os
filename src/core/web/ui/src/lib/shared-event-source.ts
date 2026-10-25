/**
 * Shared, ref-counted EventSource pool — one live SSE connection per URL
 * per tab, no matter how many components subscribe, and none while the tab
 * is hidden.
 *
 * WHY: browsers cap HTTP/1.1 at ~6 connections per origin ACROSS ALL TABS,
 * and every EventSource holds one for its lifetime. Before this pool a
 * single board tab opened 4 SSE connections (useBoardStream + AttentionBell
 * + LiveAgentsPanel on /api/stream/events, LiveStatus on /api/hooks/stream);
 * two tabs exhausted the pool and every other fetch — including index.html —
 * stalled ("the panel locks up"). Pooling alone still left 2 per tab, so a
 * few background tabs did the same; hidden tabs now release theirs. See
 * docs/engineering/hub-architecture.md#concurrency-model--never-block-the-loop-never-exhaust-the-pool
 *
 * CONTRACT for consumers:
 * - acquire with `acquireEventSource(url)`, detach listeners + `release()`
 *   on unmount. The connection closes only when the last consumer releases.
 * - attach via `source.addEventListener(...)` ONLY. The pooled stream keeps
 *   those listeners and moves them onto every reconnection.
 * - the source may already be OPEN when you acquire it (a sibling connected
 *   first), so derive initial status from `source.readyState`, not only
 *   from the `open` event.
 */

const HIDDEN_GRACE_MS = 10_000;

export type StreamSource = Pick<
  PooledStream,
  'addEventListener' | 'removeEventListener' | 'readyState' | 'close'
>;

class PooledStream {
  private connection: EventSource;
  private suspended = false;
  private readonly listeners: Array<[string, EventListenerOrEventListenerObject]> = [];

  constructor(private readonly url: string) {
    this.connection = new EventSource(url);
  }

  get readyState(): number {
    return this.suspended ? EventSource.CONNECTING : this.connection.readyState;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.push([type, listener]);
    this.connection.addEventListener(type, listener);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    const index = this.listeners.findIndex(([t, l]) => t === type && l === listener);
    if (index !== -1) this.listeners.splice(index, 1);
    this.connection.removeEventListener(type, listener);
  }

  suspend(): void {
    this.suspended = true;
    this.connection.close();
  }

  resume(): void {
    this.suspended = false;
    if (this.connection.readyState !== EventSource.CLOSED) return;
    this.connection = new EventSource(this.url);
    for (const [type, listener] of this.listeners) {
      this.connection.addEventListener(type, listener);
    }
  }

  close(): void {
    this.suspended = false;
    this.connection.close();
  }
}

interface PoolEntry {
  source: PooledStream;
  refs: number;
}

const pool = new Map<string, PoolEntry>();
let suspendTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleSuspend(): void {
  if (suspendTimer !== null) return;
  suspendTimer = setTimeout(() => {
    suspendTimer = null;
    for (const entry of pool.values()) entry.source.suspend();
  }, HIDDEN_GRACE_MS);
}

function onVisibilityChange(): void {
  if (document.visibilityState === 'hidden') {
    scheduleSuspend();
    return;
  }
  if (suspendTimer !== null) {
    clearTimeout(suspendTimer);
    suspendTimer = null;
  }
  for (const entry of pool.values()) entry.source.resume();
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', onVisibilityChange);
}

export interface SharedEventSource {
  source: StreamSource;
  release: () => void;
}

export function acquireEventSource(url: string): SharedEventSource {
  let entry = pool.get(url);
  if (!entry) {
    entry = { source: new PooledStream(url), refs: 0 };
    pool.set(url, entry);
  } else {
    // A CLOSED connection never reconnects on its own (the browser gave up);
    // reopen it in place so the holders' listeners move with it.
    entry.source.resume();
  }
  if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
    scheduleSuspend();
  }
  entry.refs += 1;
  const acquired = entry;
  let released = false;
  return {
    source: acquired.source,
    release: () => {
      if (released) return;
      released = true;
      acquired.refs -= 1;
      if (acquired.refs <= 0) {
        acquired.source.close();
        if (pool.get(url) === acquired) pool.delete(url);
      }
    },
  };
}

/** Test-only: number of live pooled connections. */
export function pooledConnectionCount(): number {
  return pool.size;
}
