import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { apiGet, resolveApiUrl } from '@/lib/api-client';
import { acquireEventSource, type SharedEventSource } from '@/lib/shared-event-source';

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
  /** A manifest agent id (the `id` field of `/api/board/list` `agent_manifest`,
   *  e.g. 'claude', 'codex', 'cursor', a future 'gemini', or 'human').
   *  Resolved from `agent_session` via `agentForSession` against the live
   *  manifest — never a hardcoded literal list. */
  agent: string;
  message: string;
  /** Status the task holds in the DB AT THIS MOMENT — useful so the UI
   *  can surface "→ now: complete" when the transition is historical
   *  and the board column no longer contains it. */
  currentStatus?: string | null;
  /** new_status emitted by this transition row — used to suppress the
   *  "now:" chip when it would just repeat `new_status` (live row).
   *  Stored separately from `message` so the renderer doesn't have to
   *  parse the human-readable string back out. */
  newStatus?: string | null;
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

const MAX_EVENTS = 400;

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

/** Resolve an `agent_session` string to a manifest agent id.
 *
 * Data-driven: scans the session against `agentIds` (the `id`s from
 * `/api/board/list` `agent_manifest`) so a future adapter is attributed
 * correctly with zero edits here. Session ids embed the agent name
 * (shape `ses-<agent>-...`). Longest matching id wins, so a future id
 * that is a superstring of another (`claude-sdk` vs `claude`) is not
 * shadowed. No match → 'human'. Pure — `agentIds` is injected, not read
 * from a context, so the function is trivially testable. */
export function agentForSession(
  session: string | null | undefined,
  agentIds: readonly string[],
): string {
  if (!session) return 'human';
  const s = session.toLowerCase();
  const match = [...agentIds]
    .filter((id) => id !== 'human' && s.includes(id.toLowerCase()))
    .sort((a, b) => b.length - a.length)[0];
  return match ?? 'human';
}

// Board-event cache keyed by pathname.  Backed by sessionStorage so it
// survives BOTH the CosBoardPage unmount/remount (nav away to Graph /
// Cognition) AND a full page reload — a reload used to flash the panel
// empty until `/api/stream/history` re-fetched ("panel keeps resetting"
// complaint).  sessionStorage (not localStorage) keeps the intent that
// the feed is browser-session-scoped: it clears when the tab closes.
const CACHE_PREFIX = 'cos-board-stream:';

function readCache(pathname: string): BoardEvent[] {
  try {
    const raw = sessionStorage.getItem(CACHE_PREFIX + pathname);
    return raw ? (JSON.parse(raw) as BoardEvent[]) : [];
  } catch {
    return [];
  }
}

function writeCache(pathname: string, events: BoardEvent[]): void {
  try {
    sessionStorage.setItem(CACHE_PREFIX + pathname, JSON.stringify(events));
  } catch {
    /* sessionStorage full / unavailable — panel still works in-memory */
  }
}

export function useBoardStream(agentIds: readonly string[]): UseBoardStreamReturn {
  const { pathname } = useLocation();
  const [bump, setBump] = useState<number>(0);
  const [connected, setConnected] = useState<boolean>(false);
  const [events, setEvents] = useState<BoardEvent[]>(
    () => readCache(pathname),
  );
  const sourceRef = useRef<EventSource | null>(null);

  const push = useCallback(
    (ev: BoardEvent) => {
      setEvents((prev) => {
        const next = [ev, ...prev];
        if (next.length > MAX_EVENTS) next.length = MAX_EVENTS;
        writeCache(pathname, next);
        return next;
      });
    },
    [pathname],
  );

  // Mirror every events-state update into the module cache so a navigate
  // -away mid-stream still keeps the rows when we navigate back.
  useEffect(() => {
    writeCache(pathname, events);
  }, [pathname, events]);

  useEffect(() => {
    let cancelled = false;
    // Keep whatever the previous mount already buffered for this
    // pathname — only seed history if the cache is empty.
    const cached = readCache(pathname);
    if (cached.length === 0) {
      setEvents([]);
    } else {
      setEvents(cached);
    }
    const loadHistory = async () => {
      try {
        const [payload] = await apiGet<StreamHistoryPayload>('/api/stream/history', { limit: 100 });
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
              agent: agentForSession(e.agent_session, agentIds),
              message: isCreate
                ? `created in ${e.new_status ?? '?'}${e.reason ? ` (${e.reason})` : ''}`
                : `${e.old_status ?? '?'} -> ${e.new_status ?? '?'}${e.reason ? ` (${e.reason})` : ''}`,
              currentStatus: e.current_status ?? null,
              newStatus: e.new_status ?? null,
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
  }, [pathname, agentIds]);

  useEffect(() => {
    let cancelled = false;
    let shared: SharedEventSource | null = null;
    try {
      shared = acquireEventSource(resolveApiUrl('/api/stream/events'));
    } catch {
      return () => undefined;
    }
    const source = shared.source;
    sourceRef.current = source;

    // Native `open` fires once the HTTP connection is established —
    // this is the authoritative "we're online" signal. The custom
    // `connected` event from the backend is kept only for logging.
    // The shared source may already be OPEN (a sibling consumer like
    // AttentionBell connected first) — `open` won't re-fire then.
    if (source.readyState === EventSource.OPEN) {
      setConnected(true);
    }
    const onOpen = () => {
      if (cancelled) return;
      setConnected(true);
    };
    source.addEventListener('open', onOpen);

    const onBackendConnected = () => {
      if (cancelled) return;
      setConnected(true);
      // De-dupe the "SSE online" row — every CosBoardPage remount opens
      // a fresh EventSource and the backend always greets with a
      // `connected` event.  Without this guard, the cached panel
      // accumulates one banner per nav-away/nav-back roundtrip.
      setEvents((prev) => {
        const recent = prev[0];
        if (recent && recent.kind === 'connected') return prev;
        const next = [
          {
            id: newId(),
            t: nowHMS(),
            kind: 'connected' as BoardEventKind,
            taskId: null,
            agent: 'human' as const,
            message: 'SSE /api/stream/events online',
          },
          ...prev,
        ];
        if (next.length > MAX_EVENTS) next.length = MAX_EVENTS;
        writeCache(pathname, next);
        return next;
      });
    };
    source.addEventListener('connected', onBackendConnected);

    // P1 — presence-updated bumps the board-list query so the live-agents
    // pill reflects state transitions without waiting for a task move.
    // Payload is informational; the bump+invalidate path does the work.
    const onPresenceUpdated = () => {
      if (cancelled) return;
      setBump((b) => b + 1);
    };
    source.addEventListener('presence-updated', onPresenceUpdated);

    // NOTE: `agent-activity` events still arrive over SSE but they are
    // NOT pushed into the Board panel — that surface is task-only.
    // Tool / hook fires belong to the Cognition → Live tab (HookStream)
    // so the Board feed stays a clean kanban-transition audit log.
    // Listeners that needed the bump (presence pill) keep getting it
    // via `presence-updated` above.
    const onAgentActivity = () => {
      if (cancelled) return;
      setBump((b) => b + 1);
    };
    source.addEventListener('agent-activity', onAgentActivity);

    const onTaskUpdated = (evt: Event) => {
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
          agent: agentForSession(data.agent_session, agentIds),
          message: `${core}${suffix}`,
          currentStatus: data.current_status ?? data.status ?? null,
          newStatus: data.new_status ?? data.status ?? null,
          transitionedAt: data.ts,
        });
      } catch {
        /* ignore malformed payload */
      }
    };
    source.addEventListener('task-updated', onTaskUpdated);

    // EventSource fires `error` on every normal auto-reconnect attempt
    // (not just real failures). Only flip to offline when the browser
    // has actually given up (readyState === CLOSED). While CONNECTING
    // we stay in the last-known state so the UI doesn't flash.
    const onError = () => {
      if (cancelled) return;
      if (source.readyState === EventSource.CLOSED) {
        setConnected(false);
      }
    };
    source.addEventListener('error', onError);

    return () => {
      cancelled = true;
      source.removeEventListener('open', onOpen);
      source.removeEventListener('connected', onBackendConnected);
      source.removeEventListener('presence-updated', onPresenceUpdated);
      source.removeEventListener('agent-activity', onAgentActivity);
      source.removeEventListener('task-updated', onTaskUpdated);
      source.removeEventListener('error', onError);
      shared?.release();
      sourceRef.current = null;
    };
    // pathname change must tear down the old connection — EventSource
    // clings to its original URL (/api/p/<old-slug>/stream/events), so
    // switching projects without this dep would leak cross-project
    // events into the new panel.
  }, [push, pathname, agentIds]);

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
