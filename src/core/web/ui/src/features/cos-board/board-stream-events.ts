// Event model for the live board stream: the wire shapes, the HH:MM:SS
// formatters, the row-dedupe key, agent attribution, and the sessionStorage
// cache. Pure — no React — so useBoardStream stays the hook and nothing else.

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
   *  e.g. 'claude', 'codex', a future 'gemini', or 'human').
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

export interface TaskUpdatedPayload {
  task_id?: string;
  old_status?: string | null;
  new_status?: string | null;
  agent_session?: string | null;
  reason?: string | null;
  source?: 'db' | 'file' | null;
  current_status?: string | null;
  ts?: number;
}

export interface StreamHistoryEvent {
  task_id?: string;
  old_status?: string | null;
  new_status?: string | null;
  agent_session?: string | null;
  reason?: string | null;
  transitioned_at?: number;
  current_status?: string | null;
}

export interface StreamHistoryPayload {
  events?: StreamHistoryEvent[];
}

export const MAX_EVENTS = 400;

export function nowHMS(): string {
  return formatHMS(new Date());
}

function formatHMS(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Render a Unix-seconds timestamp as HH:MM:SS; fall back to nowHMS
 *  when the value is missing/invalid so the panel never shows a
 *  NaN:NaN:NaN row. */
export function hmsFromEpoch(epoch: number | null | undefined): string {
  if (typeof epoch !== 'number' || !Number.isFinite(epoch) || epoch <= 0) {
    return nowHMS();
  }
  return formatHMS(new Date(epoch * 1000));
}

export function newId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

/** Key for a visually-identical stream row. Live `task-updated` events use
 *  random ids (no natural dedupe like the stable `hist-…` bootstrap ids), so
 *  a status-unchanged file rewrite that slips past the backend watermark
 *  would stack identical rows. Collapsing consecutive matches on this key is
 *  the UI-side defence-in-depth for that. */
export function liveRowKey(ev: Pick<BoardEvent, 'kind' | 'taskId' | 'message'>): string {
  return `${ev.kind}|${ev.taskId ?? ''}|${ev.message}`;
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

export function readCache(pathname: string): BoardEvent[] {
  try {
    const raw = sessionStorage.getItem(CACHE_PREFIX + pathname);
    return raw ? (JSON.parse(raw) as BoardEvent[]) : [];
  } catch {
    return [];
  }
}

export function writeCache(pathname: string, events: BoardEvent[]): void {
  try {
    sessionStorage.setItem(CACHE_PREFIX + pathname, JSON.stringify(events));
  } catch {
    /* sessionStorage full / unavailable — panel still works in-memory */
  }
}
