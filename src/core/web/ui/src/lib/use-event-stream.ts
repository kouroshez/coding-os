import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { resolveApiUrl } from '@/lib/api-client';

/**
 * Subscribe to the project-scoped SSE feed (/api/stream/events) and expose a
 * tri-state connection status the UI can show honestly. EventSource already
 * auto-reconnects with its own backoff; this hook surfaces that as
 * `reconnecting` (vs `closed`) so a silently-frozen "live" panel can never
 * mislead the human into thinking an agent is idle.
 *
 * The ONE shared SSE consumer for simple live panels (live-agents, future
 * migration of the ad-hoc EventSource sites). useBoardStream keeps its own
 * richer board-specific buffering and is intentionally NOT folded in here.
 *
 * The handler is read from a ref so changing it (a new closure every render)
 * does NOT tear down and re-open the connection — only path/scope/event-set
 * changes reconnect.
 */

export type StreamStatus = 'connecting' | 'live' | 'reconnecting' | 'closed';

export function useEventStream(
  eventTypes: readonly string[],
  onEvent: (type: string, data: unknown) => void,
  opts?: { path?: string },
): StreamStatus {
  const { pathname } = useLocation();
  const [status, setStatus] = useState<StreamStatus>('connecting');
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  const path = opts?.path ?? '/api/stream/events';
  const typesKey = eventTypes.join(',');

  useEffect(() => {
    let source: EventSource | null = null;
    try {
      source = new EventSource(resolveApiUrl(path));
    } catch {
      setStatus('closed');
      return undefined;
    }

    setStatus('connecting');
    source.onopen = () => setStatus('live');

    const types = typesKey.split(',').filter(Boolean);
    const listeners: Array<[string, (e: Event) => void]> = [];
    for (const type of types) {
      const fn = (e: Event) => {
        let parsed: unknown;
        const raw = (e as MessageEvent).data;
        if (typeof raw === 'string' && raw.length > 0) {
          try {
            parsed = JSON.parse(raw);
          } catch {
            parsed = raw;
          }
        }
        handlerRef.current(type, parsed);
      };
      source.addEventListener(type, fn);
      listeners.push([type, fn]);
    }

    // EventSource fires `error` on every auto-reconnect attempt, not only on
    // real failure: CLOSED means the browser gave up; otherwise it is mid-
    // reconnect and the last data is now stale.
    const onError = () => {
      if (!source) return;
      setStatus(source.readyState === EventSource.CLOSED ? 'closed' : 'reconnecting');
    };
    source.addEventListener('error', onError);

    return () => {
      for (const [type, fn] of listeners) source?.removeEventListener(type, fn);
      source?.removeEventListener('error', onError);
      source?.close();
    };
  }, [path, typesKey, pathname]);

  return status;
}
