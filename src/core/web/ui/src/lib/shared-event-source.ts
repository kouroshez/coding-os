/**
 * Shared, ref-counted EventSource pool — one live SSE connection per URL
 * per tab, no matter how many components subscribe.
 *
 * WHY: browsers cap HTTP/1.1 at ~6 connections per origin ACROSS ALL TABS,
 * and every EventSource holds one for its lifetime. Before this pool a
 * single board tab opened 4 SSE connections (useBoardStream + AttentionBell
 * + LiveAgentsPanel on /api/stream/events, LiveStatus on /api/hooks/stream);
 * two tabs exhausted the pool and every other fetch — including index.html —
 * stalled ("the panel locks up"). See
 * docs/engineering/hub-architecture.md#concurrency-model--never-block-the-loop-never-exhaust-the-pool
 *
 * CONTRACT for consumers:
 * - acquire with `acquireEventSource(url)`, detach listeners + `release()`
 *   on unmount. The connection closes only when the last consumer releases.
 * - attach via `source.addEventListener(...)` ONLY. Never assign
 *   `source.onopen` / `source.onmessage` — assignment clobbers the sibling
 *   consumers sharing the connection.
 * - the source may already be OPEN when you acquire it (a sibling connected
 *   first), so derive initial status from `source.readyState`, not only
 *   from the `open` event.
 */

interface PoolEntry {
  source: EventSource;
  refs: number;
}

const pool = new Map<string, PoolEntry>();

export interface SharedEventSource {
  source: EventSource;
  release: () => void;
}

export function acquireEventSource(url: string): SharedEventSource {
  let entry = pool.get(url);
  // A CLOSED source never reconnects (the browser gave up, or the last
  // consumer of a previous generation closed it) — replace, don't reuse.
  if (!entry || entry.source.readyState === EventSource.CLOSED) {
    entry = { source: new EventSource(url), refs: 0 };
    pool.set(url, entry);
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
        // Only delete if the map still points at THIS generation — a
        // replacement may already have been pooled under the same URL.
        if (pool.get(url) === acquired) pool.delete(url);
      }
    },
  };
}

/** Test-only: number of live pooled connections. */
export function pooledConnectionCount(): number {
  return pool.size;
}
