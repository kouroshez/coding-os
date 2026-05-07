import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { apiGet, resolveApiUrl } from '@/lib/api-client';

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
  | 'task-created'
  | 'human-move'
  | 'human-create'
  | 'connected'
  | 'agent'
  | 'agent-activity';

export interface BoardEvent {
  id: string; // stable key for react lists
  t: string; // HH:MM:SS in local time
  kind: BoardEventKind;
  taskId: string | null;
  agent: 'claude' | 'codex' | 'cursor' | 'human';
  message: string;
  /** Status the task holds in the DB AT THIS MOMENT — useful so the UI
   *  can surface "→ now: complete" when the transition is historical
   *  and the board column no longer contains it. */
  currentStatus?: string | null;
  /** Unix-seconds timestamp of the underlying DB row, when available.
   *  Stream-live events leave this undefined and rely on `t` for
   *  wall-clock display; history rows use it to render the actual
   *  transition time (not the page-load time). */
  transitionedAt?: number;
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
  reason?: string | null;
  source?: 'db' | 'file' | null;
  current_status?: string | null;
  ts?: number;
}

interface StreamHistoryEvent {
  task_id?: string;
  old_status?: string | null;
  new_status?: string | null;
  agent_session?: string | null;
  reason?: string | null;
  transitioned_at?: number;
  current_status?: string | null;
}

interface StreamHistoryPayload {
  events?: StreamHistoryEvent[];
}

const MAX_EVENTS = 120;

function nowHMS(): string {
  return formatHMS(new Date());
}

function formatHMS(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Render a Unix-seconds timestamp as HH:MM:SS; fall back to nowHMS
 *  when the value is missing/invalid so the panel never shows a
 *  NaN:NaN:NaN row. */
function hmsFromEpoch(epoch: number | null | undefined): string {
  if (typeof epoch !== 'number' || !Number.isFinite(epoch) || epoch <= 0) {
    return nowHMS();
  }
  return formatHMS(new Date(epoch * 1000));
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
  // React Router doesn't unmount CosBoardPage when switching between
  // /p/A/board and /p/B/board (same route pattern). We key both effects
  // below on pathname so the SSE + history bootstrap rewire to the new
  // project's scope instead of sticking to the first one opened.
  const { pathname } = useLocation();

  const push = useCallback((ev: BoardEvent) => {
    setEvents((prev) => {
      const next = [ev, ...prev];
      if (next.length > MAX_EVENTS) next.length = MAX_EVENTS;
      return next;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Wipe any events seeded by the previous project so we don't mix
    // two different histories in the same panel.
    setEvents([]);
    const loadHistory = async () => {
      try {
        const [payload] = await apiGet<StreamHistoryPayload>('/api/stream/history', { limit: 20 });
        if (cancelled) return;
        const seed = (payload?.events || [])
          .filter((e) => !!e.task_id)
          .map((e) => {
            const isCreate = e.old_status == null;
            return {
              id: `hist-${e.task_id}-${e.transitioned_at ?? 0}-${e.new_status ?? 'unknown'}`,
              // Real transition time, not the moment the panel loaded.
              // A packed 21-row bootstrap used to display the same HH:MM:SS
              // for every entry; now each row reflects when the move
              // actually happened.
              t: hmsFromEpoch(e.transitioned_at),
              kind: (isCreate ? 'task-created' : 'task-updated') as BoardEventKind,
              taskId: e.task_id || null,
              agent: agentForSession(e.agent_session),
              message: isCreate
                ? `created in ${e.new_status ?? '?'}${e.reason ? ` (${e.reason})` : ''}`
                : `${e.old_status ?? '?'} -> ${e.new_status ?? '?'}${e.reason ? ` (${e.reason})` : ''}`,
              currentStatus: e.current_status ?? null,
              transitionedAt: e.transitioned_at,
            };
          });
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
  }, [pathname]);

  useEffect(() => {
    let cancelled = false;
    let source: EventSource | null = null;
    try {
      source = new EventSource(resolveApiUrl('/api/stream/events'));
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

    // P1 — presence-updated bumps the board-list query so the live-agents
    // pill reflects state transitions without waiting for a task move.
    // Payload is informational; the bump+invalidate path does the work.
    source.addEventListener('presence-updated', () => {
      if (cancelled) return;
      setBump((b) => b + 1);
    });

    // P7 — agent fired a tool or prompt; surface as a stream-panel row
    // so the activity track stops feeling broken between task moves.
    source.addEventListener('agent-activity', (evt) => {
      if (cancelled) return;
      try {
        const data = JSON.parse((evt as MessageEvent).data) as {
          agent?: string;
          kind?: string;
          sid?: string;
          ts?: number;
        };
        const agentId = (data.agent || 'human') as 'claude' | 'codex' | 'cursor' | 'human';
        push({
          id: newId(),
          t: hmsFromEpoch(data.ts),
          kind: 'agent-activity',
          taskId: null,
          agent: agentId,
          message: `${data.kind ?? 'fired'}${data.sid ? ` · ${data.sid}` : ''}`,
        });
      } catch {
        /* ignore malformed payload */
      }
    });

    source.addEventListener('task-updated', (evt) => {
      if (cancelled) return;
      setBump((b) => b + 1);
      try {
        const data = JSON.parse((evt as MessageEvent).data) as TaskUpdatedPayload;
        const isCreate = data.old_status == null
          && data.new_status != null
          && data.source === 'db';
        const hasTransition = data.old_status || data.new_status;
        const core = isCreate
          ? `created in ${data.new_status ?? '?'}`
          : hasTransition
            ? `${data.old_status ?? '?'} -> ${data.new_status ?? data.status ?? '?'}`
            : `file changed -> status=${data.status ?? '?'}`;
        const suffix = data.reason && data.reason !== 'file edit' ? ` (${data.reason})` : '';
        push({
          id: newId(),
          // Prefer the backend ts so the clock matches the actual
          // transition, not the frame the browser happened to process it in.
          t: hmsFromEpoch(data.ts),
          kind: isCreate ? 'task-created' : 'task-updated',
          taskId: data.task_id || null,
          agent: agentForSession(data.agent_session),
          message: `${core}${suffix}`,
          currentStatus: data.current_status ?? data.status ?? null,
          transitionedAt: data.ts,
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
    // pathname change must tear down the old connection — EventSource
    // clings to its original URL (/api/p/<old-slug>/stream/events), so
    // switching projects without this dep would leak cross-project
    // events into the new panel.
  }, [push, pathname]);

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
