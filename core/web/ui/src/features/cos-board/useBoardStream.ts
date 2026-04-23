import { useCallback, useEffect, useRef, useState } from 'react';
import { apiGet } from '@/lib/api-client';

/**
 * Live board activity stream.
 *
 * PURPOSE: Maintain a rolling log of board events — SSE from the backend
 *          (agent/file-driven) plus locally-emitted human actions (drag,
 *          create) so the AGENT STREAM panel shows a unified story.
 * INPUT:   none.
 * OUTPUT:  { events, bump, connected, pushHumanEvent }.
 *   - events        rolling capped list (newest first) for the UI panel.
 *   - bump          increments on every task-updated event, so callers can
 *                   invalidate queries / refetch the board list.
 *   - connected     true while the SSE connection is open.
 *   - pushHumanEvent local-only event emitter (drag/create/other manual).
 * DEPENDENCIES: EventSource.
 * NOTES:   Heartbeats are dropped; `task-updated` events are kept and bump
 *          the refetch counter.
 */

export type BoardEventKind =
  | 'task-updated'
  | 'human-move'
  | 'human-create'
  | 'connected'
  | 'agent';

export interface BoardEvent {
  id: string; // stable key for react lists
  t: string; // HH:MM:SS in local time
  kind: BoardEventKind;
  taskId: string | null;
  agent: 'claude' | 'codex' | 'cursor' | 'human';
  message: string;
}

export interface UseBoardStreamReturn {
  bump: number;
  connected: boolean;
  events: BoardEvent[];
  pushHumanEvent: (kind: Extract<BoardEventKind, 'human-move' | 'human-create'>, opts: {
    taskId: string | null;
    message: string;
  }) => void;
}

interface TaskUpdatedPayload {
  task_id?: string;
  old_status?: string | null;
  new_status?: string | null;
  status?: string;
  agent_session?: string | null;
}

interface StreamHistoryEvent {
  task_id?: string;
  old_status?: string | null;
  new_status?: string | null;
  agent_session?: string | null;
  reason?: string | null;
  transitioned_at?: number;
}

interface StreamHistoryPayload {
  events?: StreamHistoryEvent[];
}

const MAX_EVENTS = 120;

function nowHMS(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function newId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

export function agentForSession(session: string | null | undefined): 'claude' | 'codex' | 'cursor' | 'human' {
  if (!session) return 'human';
  const s = session.toLowerCase();
  if (s.includes('claude')) return 'claude';
  if (s.includes('codex')) return 'codex';
  if (s.includes('cursor')) return 'cursor';
  return 'human';
}

export function useBoardStream(): UseBoardStreamReturn {
  const [bump, setBump] = useState<number>(0);
  const [connected, setConnected] = useState<boolean>(false);
  const [events, setEvents] = useState<BoardEvent[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  const push = useCallback((ev: BoardEvent) => {
    setEvents((prev) => {
      const next = [ev, ...prev];
      if (next.length > MAX_EVENTS) next.length = MAX_EVENTS;
      return next;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadHistory = async () => {
      try {
        const [payload] = await apiGet<StreamHistoryPayload>('/api/stream/history', { limit: 20 });
        if (cancelled) return;
        const seed = (payload?.events || [])
          .filter((e) => !!e.task_id)
          .map((e) => ({
            id: `hist-${e.task_id}-${e.transitioned_at ?? 0}-${e.new_status ?? 'unknown'}`,
            t: nowHMS(),
            kind: 'task-updated' as const,
            taskId: e.task_id || null,
            agent: agentForSession(e.agent_session),
            message: `history ${e.old_status ?? '?'} -> ${e.new_status ?? '?'}${e.reason ? ` (${e.reason})` : ''}`,
          }));
        if (seed.length === 0) return;
        setEvents((prev) => {
          const existing = new Set(prev.map((x) => x.id));
          const merged = [...seed.filter((x) => !existing.has(x.id)), ...prev];
          if (merged.length > MAX_EVENTS) merged.length = MAX_EVENTS;
          return merged;
        });
      } catch {
        // best-effort bootstrap; live SSE still works.
      }
    };
    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let source: EventSource | null = null;
    try {
      source = new EventSource('/api/stream/events');
    } catch {
      return () => undefined;
    }
    sourceRef.current = source;

    // Native `open` fires once the HTTP connection is established —
    // this is the authoritative "we're online" signal. The custom
    // `connected` event from the backend is kept only for logging.
    source.onopen = () => {
      if (cancelled) return;
      setConnected(true);
    };

    source.addEventListener('connected', () => {
      if (cancelled) return;
      setConnected(true);
      push({
        id: newId(),
        t: nowHMS(),
        kind: 'connected',
        taskId: null,
        agent: 'human',
        message: 'SSE /api/stream/events online',
      });
    });

    source.addEventListener('task-updated', (evt) => {
      if (cancelled) return;
      setBump((b) => b + 1);
      try {
        const data = JSON.parse((evt as MessageEvent).data) as TaskUpdatedPayload;
        push({
          id: newId(),
          t: nowHMS(),
          kind: 'task-updated',
          taskId: data.task_id || null,
          agent: agentForSession(data.agent_session),
          message:
            data.old_status || data.new_status
              ? `status ${data.old_status ?? '?'} -> ${data.new_status ?? data.status ?? '?'}`
              : `file changed -> status=${data.status ?? '?'}`,
        });
      } catch {
        /* ignore malformed payload */
      }
    });

    // EventSource fires `error` on every normal auto-reconnect attempt
    // (not just real failures). Only flip to offline when the browser
    // has actually given up (readyState === CLOSED). While CONNECTING
    // we stay in the last-known state so the UI doesn't flash.
    source.addEventListener('error', () => {
      if (cancelled) return;
      if (source && source.readyState === EventSource.CLOSED) {
        setConnected(false);
      }
    });

    return () => {
      cancelled = true;
      source?.close();
      sourceRef.current = null;
    };
  }, [push]);

  const pushHumanEvent = useCallback<UseBoardStreamReturn['pushHumanEvent']>(
    (kind, opts) => {
      push({
        id: newId(),
        t: nowHMS(),
        kind,
        taskId: opts.taskId,
        agent: 'human',
        message: opts.message,
      });
    },
    [push],
  );

  return { bump, connected, events, pushHumanEvent };
}
