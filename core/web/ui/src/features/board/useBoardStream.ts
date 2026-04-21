import { useEffect, useState } from 'react';

// SSE consumer. Each task-updated event triggers an invalidation bump
// so callers can re-fetch /api/board/list. Heartbeat events are
// dropped silently.
export function useBoardStream(): { bump: number; connected: boolean } {
  const [bump, setBump] = useState(0);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let source: EventSource | null = null;

    try {
      source = new EventSource('/api/stream/events');
    } catch {
      return () => undefined;
    }

    source.addEventListener('connected', () => {
      if (!cancelled) setConnected(true);
    });
    source.addEventListener('task-updated', () => {
      if (!cancelled) setBump((b) => b + 1);
    });
    source.addEventListener('error', () => {
      if (!cancelled) setConnected(false);
    });

    return () => {
      cancelled = true;
      source?.close();
    };
  }, []);

  return { bump, connected };
}
