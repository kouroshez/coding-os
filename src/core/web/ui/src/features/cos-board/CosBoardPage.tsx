import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type DragEvent,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPost, apiPatch } from '@/lib/api-client';
import { useBoardTheme } from './BoardThemeProvider';
import { useBoardStream, agentForSession, type BoardEvent } from './useBoardStream';
import { renderTaskMarkdown, splitFrontmatter } from './renderTaskMarkdown';
import { KIND_COLORS, kindStyle } from './kindColors';
import type {
  AgentPresence,
  BoardAgentManifestEntry,
  BoardConfigPayload,
  BoardListCard,
  BoardListPayload,
  BoardTweaks,
  ColumnDTO,
  SwimlaneDTO,
} from './types';
import { visualFor } from './agentPresenceVisuals';

// ---------- types ----------
type HighlightKind = 'kind' | 'swim' | 'priority';
interface Highlight {
  type: HighlightKind;
  value: string;
}

interface TaskCounts {
  kind: Record<string, number>;
  swim: Record<string, number>;
  priority: Record<string, number>;
}

interface CreateTaskForm {
  title: string;
  swimlane: string;
  kind: string;
  priority: string;
  appetite: string;
  epic?: string | null;
  labels?: string[];
  outcome?: string | null;
}

interface CreateTaskResponse {
  task_id?: string;
  data?: { task_id?: string };
}

// ---------- static data (prototype parity) ----------
// Column ordering matches the Scrumban state machine in
// core/board_os/workflow.py::_VALID_TRANSITIONS. "ready" is no longer a
// column — it lives as an optional label on icebox tasks (see
// READY_LABEL in core/board_os/config.py).  Archive is hidden by
// default and opts in via BoardTweaks.showArchive.
const COLUMN_META: Record<string, { label: string; sub: string; wip: number | null }> = {
  icebox: { label: 'ICE BOX', sub: 'backlog · tag “ready”', wip: null },
  emergency: { label: 'EMERGENCY', sub: 'fire — skip queue', wip: 2 },
  in_progress: { label: 'IN PROGRESS', sub: 'active work', wip: 1 },
  testing: { label: 'TESTING', sub: 'verifying G/W/T', wip: 3 },
  blocked: { label: 'BLOCKED', sub: 'external dep', wip: null },
  complete: { label: 'COMPLETE', sub: 'acceptance met', wip: null },
  archive: { label: 'ARCHIVE', sub: 'frozen', wip: null },
};

// Fallback when GET /api/board/list has no `agent_manifest` (older Hub).
const FALLBACK_AGENT_MANIFEST: BoardAgentManifestEntry[] = [
  { id: 'claude', color: '#d97706', label: 'claude', glyph: 'Cl', session: 'ses-claude' },
  { id: 'codex', color: '#0891b2', label: 'codex', glyph: 'Cx', session: 'ses-codex' },
  { id: 'cursor', color: '#6366f1', label: 'cursor', glyph: 'Cr', session: 'ses-cursor' },
  { id: 'human', color: '#16a34a', label: 'human', glyph: 'H', session: 'local-mac' },
];

const AgentCatalogContext = createContext<BoardAgentManifestEntry[]>(FALLBACK_AGENT_MANIFEST);

function useAgentCatalog(): BoardAgentManifestEntry[] {
  return useContext(AgentCatalogContext);
}

const EVENT_COLOR: Record<string, string> = {
  'task-updated': '#7c3aed',
  'task-created': '#16a34a',
  'human-move': '#d97706',
  'human-create': '#16a34a',
  connected: '#0891b2',
  agent: '#0891b2',
};

const EVENT_LABEL: Record<string, string> = {
  'task-updated': 'update',
  'task-created': 'create',
  'human-move': 'drag',
  'human-create': 'create',
  connected: 'sse',
  agent: 'agent',
};

// ---------- helpers ----------
/** Parse #rgb or #rrggbb into [r, g, b] 0..255, or null. */
function parseHex(hex: string): [number, number, number] | null {
  const s = hex.replace('#', '').trim();
  if (s.length === 3) {
    const r = parseInt(s[0] + s[0], 16);
    const g = parseInt(s[1] + s[1], 16);
    const b = parseInt(s[2] + s[2], 16);
    return Number.isFinite(r + g + b) ? [r, g, b] : null;
  }
  if (s.length === 6) {
    const r = parseInt(s.slice(0, 2), 16);
    const g = parseInt(s.slice(2, 4), 16);
    const b = parseInt(s.slice(4, 6), 16);
    return Number.isFinite(r + g + b) ? [r, g, b] : null;
  }
  return null;
}

function rgbToHex(r: number, g: number, b: number): string {
  const to = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
  return `#${to(r)}${to(g)}${to(b)}`;
}

/** Darken a hex colour by `pct` (0..1). Used when config.accent === config.color. */
function darken(hex: string, pct: number): string {
  const rgb = parseHex(hex);
  if (!rgb) return hex;
  const [r, g, b] = rgb;
  const f = 1 - pct;
  return rgbToHex(r * f, g * f, b * f);
}

/** rgba(r,g,b,a) string for a hex colour; a in 0..1. */
function alpha(hex: string, a: number): string {
  const rgb = parseHex(hex);
  if (!rgb) return hex;
  const [r, g, b] = rgb;
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

/**
 * Given the SwimlaneDTO from the backend, return the palette pair we
 * actually render: `color` (row tint / band fill) and `accent` (text /
 * border). If config didn't supply a distinct accent we darken the
 * primary colour by ~30% so every lane keeps crisp contrast.
 */
function lanePalette(lane: SwimlaneDTO): { color: string; accent: string } {
  const color = lane.color || '#6b7280';
  const accent = lane.accent && lane.accent !== lane.color ? lane.accent : darken(color, 0.3);
  return { color, accent };
}


function columnWipCap(colId: string, wip: BoardConfigPayload['wip_limits'] | undefined): number | null {
  if (wip) {
    if (colId === 'in_progress') return wip.in_progress;
    if (colId === 'testing') return wip.testing;
    if (colId === 'emergency') return wip.emergency;
  }
  return COLUMN_META[colId]?.wip ?? null;
}

function priorityStyle(priority: string): CSSProperties {
  // Calm + themed: only P0/P1 carry a single thin outline; P2/P3 rely on
  // the priority text badge so the board isn't a wall of red/orange frames.
  switch (priority) {
    case 'P0':
      return { outline: '1.5px solid var(--cos-err)', outlineOffset: 1 };
    case 'P1':
      return { outline: '1px solid var(--cos-warn)' };
    default:
      return {};
  }
}

// AgentState reuses the AgentPresence alias from types so backend and
// frontend agree on spelling.  Visual mapping lives in
// agentPresenceVisuals.ts — its exhaustive Record<AgentPresence, …>
// forces a TS build error the moment a new backend variant is added
// without a matching visual, so we can't silently under-paint a state.
export type AgentState = AgentPresence;

function AgentBadge({
  agentId,
  state,
  sessionCount,
}: {
  agentId: string;
  state: AgentState;
  sessionCount?: number;
}) {
  const catalog = useAgentCatalog();
  const a = catalog.find((x) => x.id === agentId);
  if (!a) return null;
  const dot = visualFor(state);
  const live = state !== 'offline';
  // Border = STATE color (not brand) so the pill itself signals presence.
  // Brand color survives in the faint background tint + label color, so
  // adapter identity stays readable without competing with state.
  // Fixes the regression where Claude's amber brand made every Claude
  // pill look like it was in `present` (also amber) regardless of state.
  const borderColor = live ? dot.color : 'var(--col-border)';
  return (
    <div
      title={`${a.label} — ${dot.label}${sessionCount && sessionCount > 1 ? ` (${sessionCount} sessions)` : ''}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        padding: '3px 8px 3px 6px',
        borderRadius: 999,
        background: live ? `${a.color}12` : 'var(--board-grain)',
        border: `1.5px solid ${borderColor}`,
        color: live ? a.color : 'var(--ink-faint)',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
        fontWeight: 600,
        transition: 'all 0.2s',
      }}
    >
      <span
        style={{
          width: 9,
          height: 9,
          borderRadius: '50%',
          background: dot.color,
          boxShadow: `0 0 0 2px ${dot.ring}`,
          animation: dot.pulse ? 'cos-agent-pulse 1.4s ease-in-out infinite' : undefined,
        }}
      />
      {a.label}
      {sessionCount && sessionCount > 1 ? (
        <span style={{ opacity: 0.85, fontWeight: 700 }}>·{sessionCount}</span>
      ) : null}
    </div>
  );
}

function AgentPip({ agentId, title, size = 18 }: { agentId?: string | null; title?: string; size?: number }) {
  // Hook must run unconditionally — call before the early return (rules-of-hooks).
  const catalog = useAgentCatalog();
  if (!agentId) return null;
  const a = catalog.find((x) => x.id === agentId);
  if (!a) return null;
  // Two-letter glyphs need a tighter font to fit inside the pip cleanly.
  const glyphRatio = a.glyph.length > 1 ? 0.44 : 0.58;
  return (
    <span
      title={title || `${a.label} (${a.session})`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        borderRadius: '50%',
        background: a.color,
        color: 'white',
        fontSize: Math.round(size * glyphRatio),
        fontWeight: 700,
        fontFamily: "'JetBrains Mono', monospace",
        letterSpacing: a.glyph.length > 1 ? '-0.5px' : undefined,
        boxShadow: '0 2px 4px rgba(0,0,0,.15)',
        border: '2px solid rgba(255,255,255,0.85)',
      }}
    >
      {a.glyph}
    </span>
  );
}

// ============================================================
// Main page
// ============================================================
export default function CosBoardPage() {
  const qc = useQueryClient();
  const { tweaks, setTweaks } = useBoardTheme();
  const { bump, connected, events: streamEvents, pushHumanEvent } = useBoardStream();

  const { data: list, isLoading, error } = useApiGet<BoardListPayload>(
    ['board-list'],
    '/api/board/list',
    { limit: 400, include_archive: true },
  );
  const { data: cfg } = useApiGet<BoardConfigPayload>(['board-config'], '/api/board/config');

  useEffect(() => {
    if (bump > 0) {
      // queryKey prefix is ['cos-scope', slug, path, ...] — a plain-path
      // queryKey no longer matches.  `invalidateApiQueries` uses a
      // predicate so both scoped and unscoped entries with the given
      // path get invalidated.
      void invalidateApiQueries(qc, '/api/board/list');
      void invalidateApiQueries(qc, '/api/board/retro');
    }
  }, [bump, qc]);

  const [zoom, setZoom] = useState<number>(() => {
    const v = parseFloat(localStorage.getItem('cos-zoom') || '1');
    return Number.isFinite(v) && v >= 0.5 && v <= 1.5 ? v : 1;
  });
  const [collapsed, setCollapsed] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('cos-collapsed-lanes') || '[]') as string[]);
    } catch {
      return new Set();
    }
  });
  const [streamOpen, setStreamOpen] = useState<boolean>(true);
  const [legendOpen, setLegendOpen] = useState<boolean>(false);
  const [tweaksOpen, setTweaksOpen] = useState<boolean>(false);
  const [createOpen, setCreateOpen] = useState<boolean>(false);
  const [detailTask, setDetailTask] = useState<BoardListCard | null>(null);

  const [dragging, setDragging] = useState<BoardListCard | null>(null);
  const [dragTarget, setDragTarget] = useState<string | null>(null);
  const [flashWip, setFlashWip] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<Highlight | null>(null);

  useEffect(() => {
    localStorage.setItem('cos-zoom', String(zoom));
  }, [zoom]);
  useEffect(() => {
    localStorage.setItem('cos-collapsed-lanes', JSON.stringify([...collapsed]));
  }, [collapsed]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (e.key === 'n' && !e.metaKey && !e.ctrlKey && tag !== 'INPUT' && tag !== 'TEXTAREA') {
        e.preventDefault();
        setCreateOpen(true);
      }
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === '=' || e.key === '+') {
        e.preventDefault();
        setZoom((z) => Math.min(1.5, Math.max(0.5, Math.round((z + 0.1) * 100) / 100)));
      } else if (e.key === '-') {
        e.preventDefault();
        setZoom((z) => Math.min(1.5, Math.max(0.5, Math.round((z - 0.1) * 100) / 100)));
      } else if (e.key === '0') {
        e.preventDefault();
        setZoom(1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const cards: BoardListCard[] = list?.cards ?? [];
  const swimlanes: SwimlaneDTO[] = cfg?.swimlanes ?? [];
  // Filter archive out of the visible column list unless the user opts
  // in via the header toggle — archive is a soft-terminal cold store and
  // most sessions don't need to see it.  Backend still returns archive
  // cards in `cards`, so the only concession when hidden is that those
  // cards can't be reached from the main grid (drawer deep-link still
  // works for historical references).
  const allColumns: ColumnDTO[] = cfg?.columns ?? [];
  const columns: ColumnDTO[] = useMemo(
    () => allColumns.filter((c) => c.id !== 'archive' || tweaks.showArchive),
    [allColumns, tweaks.showArchive],
  );

  const filtered = useMemo<BoardListCard[]>(
    () =>
      cards.filter((t) => {
        if (tweaks.filterKind !== 'all' && t.kind !== tweaks.filterKind) return false;
        if (tweaks.filterEpic !== 'all' && (t.epic || '') !== tweaks.filterEpic) return false;
        if (tweaks.filterSwim !== 'all' && t.swimlane !== tweaks.filterSwim) return false;
        return true;
      }),
    [cards, tweaks.filterKind, tweaks.filterEpic, tweaks.filterSwim],
  );

  const cellMap = useMemo<Record<string, Record<string, BoardListCard[]>>>(() => {
    const m: Record<string, Record<string, BoardListCard[]>> = {};
    for (const sl of swimlanes) {
      m[sl.id] = {};
      for (const c of columns) m[sl.id][c.id] = [];
    }
    for (const t of filtered) {
      if (m[t.swimlane]?.[t.status]) m[t.swimlane][t.status].push(t);
    }
    return m;
  }, [filtered, swimlanes, columns]);

  const taskCounts = useMemo<TaskCounts>(() => {
    const c: TaskCounts = { kind: {}, swim: {}, priority: {} };
    for (const t of cards) {
      c.kind[t.kind] = (c.kind[t.kind] || 0) + 1;
      c.swim[t.swimlane] = (c.swim[t.swimlane] || 0) + 1;
      c.priority[t.priority] = (c.priority[t.priority] || 0) + 1;
    }
    return c;
  }, [cards]);

  const kindOptions = useMemo<{ value: string; label: string }[]>(
    () => [{ value: 'all', label: 'all' }, ...Object.keys(KIND_COLORS).map((k) => ({ value: k, label: kindStyle(k).label }))],
    [],
  );
  const epicOptions = useMemo<{ value: string; label: string }[]>(
    () => [
      { value: 'all', label: 'all' },
      ...Array.from(new Set(cards.map((t) => t.epic).filter((e): e is string => !!e))).map((e) => ({
        value: e,
        label: e,
      })),
    ],
    [cards],
  );

  // ---------- DnD ----------
  const onDragStart = (e: DragEvent, task: BoardListCard) => {
    setDragging(task);
    e.dataTransfer.effectAllowed = 'move';
    try {
      e.dataTransfer.setData('text/plain', task.id);
    } catch {
      /* ignore */
    }
  };
  const onDragEnd = () => {
    setDragging(null);
    setDragTarget(null);
  };
  const onDragOver = (e: DragEvent, laneId: string, colId: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragTarget(`${laneId}:${colId}`);
  };
  const onDrop = async (e: DragEvent, laneId: string, colId: string) => {
    e.preventDefault();
    if (!dragging) return;
    if (dragging.status === colId && dragging.swimlane === laneId) return onDragEnd();

    // Ready-gate pre-flight (mirrors workflow.transition): an icebox task
    // without the 'ready' label cannot be pulled into in_progress. Surface it
    // client-side with an actionable message instead of a generic server
    // "invalid transition" after the round-trip.
    if (
      colId === 'in_progress' &&
      dragging.status === 'icebox' &&
      !(dragging.labels ?? []).includes('ready')
    ) {
      setActionError(
        `${dragging.id} is not ready — open it and "mark ready" before pulling into in_progress.`,
      );
      return onDragEnd();
    }

    const cap = columnWipCap(colId, cfg?.wip_limits);
    const inCol = filtered.filter((t) => t.status === colId && t.id !== dragging.id).length;
    if (cap != null && inCol >= cap && tweaks.showWipViolation) {
      setFlashWip(colId);
      setTimeout(() => setFlashWip(null), 1200);
    }
    setActionError(null);
    const parts: string[] = [];
    if (dragging.status !== colId) parts.push(`${dragging.status} → ${colId}`);
    if (dragging.swimlane !== laneId) parts.push(`lane ${dragging.swimlane} → ${laneId}`);
    pushHumanEvent('human-move', {
      taskId: dragging.id,
      message: parts.join(' · ') || 'no-op',
    });
    const tryMove = async (force: boolean) => {
      await apiPost('/api/board/reposition', {
        task_id: dragging.id,
        to: dragging.status === colId ? undefined : colId,
        swimlane: dragging.swimlane === laneId ? undefined : laneId,
        force,
        reason: force ? 'human drag (forced)' : undefined,
      });
      await invalidateApiQueries(qc, '/api/board/list');
      await invalidateApiQueries(qc, '/api/board/retro');
    };

    try {
      await tryMove(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'move failed';
      // If the state machine rejected this drop, offer the user an
      // explicit opt-in force retry.  Anything else (network, 5xx,
      // "task not found") is surfaced as-is.
      const looksLikeInvalidTransition = /invalid transition/i.test(msg);
      if (looksLikeInvalidTransition && typeof window !== 'undefined'
          && window.confirm(
            `${msg}\n\nDrop it anyway? This will be recorded as a `
            + 'forced transition in the task history.',
          )) {
        try {
          await tryMove(true);
          pushHumanEvent('human-move', {
            taskId: dragging.id,
            message: `${parts.join(' · ')} (forced)`,
          });
          onDragEnd();
          return;
        } catch (err2) {
          const msg2 = err2 instanceof Error ? err2.message : 'force move failed';
          setActionError(msg2);
          pushHumanEvent('human-move', {
            taskId: dragging.id,
            message: `FAILED (force) — ${msg2}`,
          });
          onDragEnd();
          return;
        }
      }
      setActionError(msg);
      pushHumanEvent('human-move', { taskId: dragging.id, message: `FAILED — ${msg}` });
    }
    onDragEnd();
  };

  const clampZoom = (v: number) => Math.min(1.5, Math.max(0.5, Math.round(v * 100) / 100));

  // Rules-of-Hooks: every hook MUST execute before any conditional return,
  // otherwise the second render adds a hook the first did not call and
  // React throws "Rendered more hooks than during the previous render."
  // (#310). agentCatalog used to live after the loading/error guards;
  // moved up to keep the call count stable across renders.
  const agentCatalog = useMemo(
    () =>
      list?.agent_manifest && list.agent_manifest.length > 0
        ? list.agent_manifest
        : FALLBACK_AGENT_MANIFEST,
    [list?.agent_manifest],
  );

  // ---------- render ----------
  if (isLoading) {
    return (
      <div style={{ padding: 24, fontFamily: "'JetBrains Mono', monospace", color: 'var(--ink-soft)' }}>
        loading board…
      </div>
    );
  }
  if (error) {
    return (
      <div style={{ padding: 24, fontFamily: "'JetBrains Mono', monospace", color: 'var(--cos-err)' }}>
        {error.message}
      </div>
    );
  }

  const totalWidth = Math.max(400, columns.length * 200 + 130);

  return (
    <AgentCatalogContext.Provider value={agentCatalog}>
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <TopBar
        taskCount={list?.count ?? 0}
        connected={connected}
        cursorModel={list?.cursor_model}
        sessionCounts={list?.session_counts ?? {}}
        agentStates={
          list?.agent_states ?? (
            // Back-compat: pre-0.5 backends only send active_agents list.
            (list?.active_agents ?? ['human']).reduce<Record<string, AgentState>>(
              (acc, id) => ({ ...acc, [id]: 'active' }),
              {},
            )
          )
        }
        legendOpen={legendOpen}
        streamOpen={streamOpen}
        showArchive={tweaks.showArchive}
        onToggleLegend={() => setLegendOpen((v) => !v)}
        onToggleStream={() => setStreamOpen((v) => !v)}
        onToggleArchive={() => setTweaks((t) => ({ ...t, showArchive: !t.showArchive }))}
        onToggleTweaks={() => setTweaksOpen((v) => !v)}
        onCreate={() => setCreateOpen(true)}
      />

      {actionError && (
        <div
          style={{
            padding: '6px 12px',
            background: 'rgba(220,38,38,.12)',
            borderBottom: '1px solid rgba(220,38,38,.35)',
            color: 'var(--cos-err)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
          }}
        >
          {actionError}
        </div>
      )}

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: 'auto',
          position: 'relative',
          paddingRight: streamOpen ? 396 : 0,
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            zoom,
            width: '100%',
            minWidth: totalWidth,
            minHeight: '100%',
          } as CSSProperties}
        >
          <div
            style={{
              display: 'flex',
              position: 'sticky',
              top: 0,
              zIndex: 5,
              background: 'var(--board)',
              borderBottom: '2px solid var(--line)',
            }}
          >
            <div
              style={{
                width: 130,
                minWidth: 130,
                flexShrink: 0,
                borderRight: '2px solid var(--line)',
                position: 'sticky',
                left: 0,
                zIndex: 2,
                background: 'var(--board)',
              }}
            />
            {columns.map((col) => {
              const count = filtered.filter((t) => t.status === col.id).length;
              const meta = COLUMN_META[col.id] ?? { label: col.label, sub: '', wip: null };
              const cap = columnWipCap(col.id, cfg?.wip_limits);
              const violated = tweaks.showWipViolation && cap != null && count > cap;
              return (
                <div
                  key={col.id}
                  style={{ flex: '1 1 0', minWidth: 190, borderRight: '1px dashed var(--col-border)' }}
                >
                  <div
                    style={{
                      position: 'sticky',
                      top: 0,
                      padding: '10px 12px 8px',
                      background: violated ? 'rgba(192,57,43,.12)' : 'transparent',
                      textAlign: 'center',
                    }}
                  >
                    <div
                      style={{
                        fontFamily: 'inherit',
                        fontSize: 17,
                        letterSpacing: '.08em',
                        color: violated ? 'var(--red-ink)' : 'var(--line)',
                        textTransform: 'uppercase',
                        animation: violated ? 'shake 0.6s infinite' : 'none',
                      }}
                    >
                      {meta.label}
                    </div>
                    <div style={{ fontFamily: 'inherit', fontSize: 13, color: 'var(--ink-soft)', marginTop: -2 }}>
                      {meta.sub}
                    </div>
                    <div
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 10,
                        color: violated ? 'var(--red-ink)' : 'var(--ink-faint)',
                        marginTop: 2,
                        fontWeight: violated ? 700 : 500,
                      }}
                    >
                      {count}
                      {cap != null ? ` / ${cap} wip` : ''}
                      {violated && ' ⚠'}
                      {flashWip === col.id && <span style={{ marginLeft: 6 }}>WIP</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {swimlanes.map((lane, laneIdx) => {
            const laneCount = filtered.filter((t) => t.swimlane === lane.id).length;
            const isCollapsed = collapsed.has(lane.id);
            const palette = lanePalette(lane);
            if (isCollapsed) {
              return (
                <div
                  key={lane.id}
                  onClick={() =>
                    setCollapsed((prev) => {
                      const n = new Set(prev);
                      n.delete(lane.id);
                      return n;
                    })
                  }
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '7px 14px 7px 20px',
                    borderBottom: '1px solid var(--col-border)',
                    borderLeft: `6px solid ${palette.accent}`,
                    background: alpha(palette.color, 0.06),
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    fontSize: 14,
                    color: palette.accent,
                    position: 'sticky',
                    left: 0,
                  }}
                >
                  <span style={{ color: 'var(--ink-faint)', fontSize: 12 }}>▸</span>
                  <span>{lane.label}</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: 'var(--ink-faint)', fontWeight: 500 }}>
                    · {laneCount} task{laneCount !== 1 ? 's' : ''}
                  </span>
                  <span style={{ flex: 1 }} />
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: 'var(--ink-faint)' }}>
                    click to expand
                  </span>
                </div>
              );
            }
            const rowTint = alpha(palette.color, laneIdx % 2 ? 0.05 : 0.035);
            return (
              <div
                key={lane.id}
                style={{
                  display: 'flex',
                  borderBottom: '1px solid var(--col-border)',
                  background: rowTint,
                  minHeight: 140,
                }}
              >
                <SwimlaneLabel
                  lane={lane}
                  palette={palette}
                  taskCount={laneCount}
                  onCollapse={() =>
                    setCollapsed((prev) => {
                      const n = new Set(prev);
                      n.add(lane.id);
                      return n;
                    })
                  }
                />
                {columns.map((col) => {
                  const cell = cellMap[lane.id]?.[col.id] ?? [];
                  const isTarget = dragTarget === `${lane.id}:${col.id}`;
                  const cap = columnWipCap(col.id, cfg?.wip_limits);
                  const violated = cap != null && cell.length > cap;
                  return (
                    <div
                      key={col.id}
                      onDragOver={(e) => onDragOver(e, lane.id, col.id)}
                      onDrop={(e) => void onDrop(e, lane.id, col.id)}
                      style={{
                        flex: '1 1 0',
                        minWidth: 190,
                        padding: tweaks.density === 'cozy' ? '10px 10px 8px' : '6px 7px 5px',
                        borderRight: '1px dashed var(--col-border)',
                        background: isTarget
                          ? 'rgba(217, 108, 44, .08)'
                          : violated
                            ? 'rgba(192,57,43,.04)'
                            : 'transparent',
                        minHeight: 120,
                        transition: 'background .1s ease',
                      }}
                    >
                      {cell.map((task) => (
                        <TaskStickyCard
                          key={task.id}
                          task={task}
                          laneColor={palette.color}
                          laneAccent={palette.accent}
                          density={tweaks.density}
                          quietMode={tweaks.quietMode}
                          agentSurface={tweaks.agentSurface}
                          highlight={highlight}
                          draggingId={dragging?.id || ''}
                          onDragStart={onDragStart}
                          onDragEnd={onDragEnd}
                          onOpen={setDetailTask}
                        />
                      ))}
                      {cell.length === 0 && (
                        <div
                          style={{
                            fontFamily: 'inherit',
                            fontSize: 14,
                            color: 'var(--ink-faint)',
                            textAlign: 'center',
                            padding: '20px 4px',
                            opacity: 0.5,
                          }}
                        >
                          — empty —
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}

          <div
            style={{
              padding: '14px 18px 28px',
              fontFamily: 'inherit',
              fontSize: 14,
              color: 'var(--ink-faint)',
              textAlign: 'center',
            }}
          >
            drag cards between columns · WIP caps enforced by workflow.transition() · SSoT is the Markdown frontmatter
          </div>
          <div
            aria-hidden
            style={{
              minHeight: '40vh',
              borderTop: '1px dashed var(--col-border)',
              background:
                'repeating-linear-gradient(0deg, transparent 0 39px, rgba(0,0,0,.04) 39px 40px)',
              opacity: 0.6,
            }}
          />
        </div>

        <ZoomControls
          zoom={zoom}
          setZoom={(v) => setZoom(clampZoom(v))}
          collapsedCount={collapsed.size}
          onExpandAll={() => setCollapsed(new Set())}
          onCollapseEmpty={() => {
            const empty = new Set<string>();
            for (const l of swimlanes) {
              if (!cards.some((t) => t.swimlane === l.id)) empty.add(l.id);
            }
            setCollapsed(empty);
          }}
        />
      </div>

      <LiveStreamPanel
        open={streamOpen && tweaks.agentSurface}
        onClose={() => setStreamOpen(false)}
        events={streamEvents}
        connected={connected}
      />
      <LegendPanel
        open={legendOpen}
        onClose={() => setLegendOpen(false)}
        swimlanes={swimlanes}
        filterKind={tweaks.filterKind}
        setFilterKind={(v) => setTweaks((t) => ({ ...t, filterKind: v }))}
        filterSwim={tweaks.filterSwim}
        setFilterSwim={(v) => setTweaks((t) => ({ ...t, filterSwim: v }))}
        highlight={highlight}
        setHighlight={setHighlight}
        taskCounts={taskCounts}
      />
      <TweaksPanel
        open={tweaksOpen}
        onClose={() => setTweaksOpen(false)}
        tweaks={tweaks}
        setTweaks={setTweaks}
        kindOptions={kindOptions}
        epicOptions={epicOptions}
      />

      <CreateTaskModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        swimlanes={swimlanes}
        nextId={
          (cards.reduce((m, t) => Math.max(m, parseInt(String(t.id).replace('TASK-', ''), 10) || 0), 0) || 200) + 1
        }
        onCreate={async (form) => {
          setActionError(null);
          try {
            const [payload] = await apiPost<CreateTaskResponse>('/api/board/create', form);
            const id = payload?.data?.task_id ?? payload?.task_id ?? form.title;
            setCreateOpen(false);
            setJustCreated(id);
            pushHumanEvent('human-create', {
              taskId: typeof id === 'string' ? id : null,
              message: `${form.kind} · lane ${form.swimlane} · ${form.priority} · "${form.title}"`,
            });
            setTimeout(() => setJustCreated(null), 2800);
            await invalidateApiQueries(qc, '/api/board/list');
            await invalidateApiQueries(qc, '/api/board/retro');
          } catch (err) {
            const msg = err instanceof Error ? err.message : 'create failed';
            setActionError(msg);
            pushHumanEvent('human-create', { taskId: null, message: `FAILED — ${msg}` });
          }
        }}
      />

      <TaskDetailDrawer
        task={detailTask}
        swimlanes={swimlanes}
        onClose={() => setDetailTask(null)}
      />

      {justCreated && (
        <div
          style={{
            position: 'fixed',
            bottom: 22,
            left: '50%',
            transform: 'translateX(-50%)',
            padding: '10px 18px',
            background: 'var(--cos-ok)',
            color: 'white',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 12,
            fontWeight: 600,
            borderRadius: 4,
            zIndex: 150,
            boxShadow: '0 10px 25px rgba(0,0,0,.25)',
            animation: 'fadeIn .2s ease',
          }}
        >
          ✓ created {justCreated} · validate-task-frontmatter.sh → ok · sync v13 → ok
        </div>
      )}
    </div>
    </AgentCatalogContext.Provider>
  );
}

// ============================================================
// TopBar
// ============================================================
function TopBar({
  taskCount,
  connected,
  cursorModel,
  agentStates,
  sessionCounts,
  legendOpen,
  streamOpen,
  showArchive,
  onToggleLegend,
  onToggleStream,
  onToggleArchive,
  onToggleTweaks,
  onCreate,
}: {
  taskCount: number;
  connected: boolean;
  cursorModel?: string | null;
  agentStates: Record<string, AgentState>;
  sessionCounts?: Record<string, number>;
  legendOpen: boolean;
  streamOpen: boolean;
  showArchive: boolean;
  onToggleLegend: () => void;
  onToggleStream: () => void;
  onToggleArchive: () => void;
  onToggleTweaks: () => void;
  onCreate: () => void;
}) {
  const agentRows = useAgentCatalog();
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 18px',
        borderBottom: '1px solid var(--col-border)',
        background:
          'linear-gradient(180deg, var(--board) 0%, color-mix(in srgb, var(--board) 92%, var(--board-grain)) 100%)',
        position: 'relative',
        zIndex: 10,
        flexWrap: 'wrap',
        minHeight: 48,
      }}
    >
      <div style={{ flex: 1 }} />

      {/* LIVE STATUS + ACTIONS */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
        <div
          title={`${taskCount} tasks · sse ${connected ? 'online' : 'offline'}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <span style={{ color: 'var(--ink-faint)', fontSize: 13 }}>live:</span>
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
            {agentRows.map((a) => (
              <AgentBadge
                key={a.id}
                agentId={a.id}
                state={agentStates[a.id] ?? 'offline'}
                sessionCount={sessionCounts?.[a.id]}
              />
            ))}
          </div>
          {cursorModel && agentStates.cursor && agentStates.cursor !== 'offline' ? (
            <span
              title="display-only: .coding-os/cursor/.model"
              style={{ color: 'var(--ink-faint)', fontSize: 10, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              model: {cursorModel}
            </span>
          ) : null}
          <span
            style={{
              color: connected ? 'var(--cos-ok)' : 'var(--cos-faint)',
              fontSize: 13,
              fontWeight: 600,
              marginLeft: 4,
            }}
          >
            {connected ? 'sse' : 'off'}
          </span>
          <span style={{ color: 'var(--ink-faint)', fontSize: 13 }}>· {taskCount}</span>
        </div>

        <div style={{ width: 1, height: 22, background: 'var(--col-border)', margin: '0 2px' }} />

        <button
          type="button"
          onClick={onCreate}
          title="New task (n)"
          style={{
            padding: '6px 14px',
            fontSize: 11,
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 700,
            background: 'var(--accent)',
            color: 'white',
            border: '1px solid var(--accent)',
            borderRadius: 4,
            cursor: 'pointer',
            letterSpacing: '.04em',
            boxShadow: '0 1px 2px rgba(217,108,44,.3)',
          }}
        >
          ＋ new
        </button>

        <TopBtn onClick={onToggleLegend} active={legendOpen}>⁂ legend</TopBtn>
        <TopBtn onClick={onToggleStream} active={streamOpen}>⎌ stream</TopBtn>
        <TopBtn onClick={onToggleArchive} active={showArchive}>
          {showArchive ? '▣ archive on' : '▢ archive'}
        </TopBtn>
        <TopBtn onClick={onToggleTweaks}>⚙ tweaks</TopBtn>
      </div>
    </div>
  );
}

function TopBtn({
  children,
  onClick,
  active,
}: {
  children: ReactNode;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '6px 10px',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        fontWeight: 600,
        background: active ? 'var(--accent)' : 'transparent',
        color: active ? 'white' : 'var(--ink)',
        border: `1.5px solid ${active ? 'var(--accent)' : 'var(--line-soft)'}`,
        borderRadius: 4,
        cursor: 'pointer',
      }}
    >
      {children}
    </button>
  );
}

// ============================================================
// Swimlane label
// ============================================================
function SwimlaneLabel({
  lane,
  palette,
  taskCount,
  onCollapse,
}: {
  lane: SwimlaneDTO;
  palette: { color: string; accent: string };
  taskCount: number;
  onCollapse: () => void;
}) {
  return (
    <div
      style={{
        position: 'sticky',
        left: 0,
        zIndex: 4,
        width: 130,
        minWidth: 130,
        flexShrink: 0,
        alignSelf: 'stretch',
        padding: '12px 10px',
        background: `linear-gradient(90deg, ${alpha(palette.color, 0.14)} 0%, var(--board) 100%)`,
        borderRight: `3px solid ${palette.accent}`,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        boxSizing: 'border-box',
      }}
    >
      <button
        type="button"
        onClick={onCollapse}
        title="Collapse lane"
        style={{
          position: 'absolute',
          top: 6,
          right: 6,
          width: 18,
          height: 18,
          background: 'transparent',
          border: 'none',
          color: 'var(--ink-faint)',
          cursor: 'pointer',
          fontSize: 12,
          lineHeight: 1,
          padding: 0,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        ▾
      </button>
      <div
        style={{
          fontFamily: 'inherit',
          fontSize: 15,
          color: palette.accent,
          letterSpacing: '.02em',
          whiteSpace: 'normal',
          overflowWrap: 'anywhere',
          wordBreak: 'break-word',
          lineHeight: 1.2,
          maxWidth: '100%',
        }}
      >
        {lane.label}
      </div>
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: 'var(--ink-faint)', marginTop: 2 }}>
        {taskCount} tasks
      </div>
      <div style={{ width: 40, height: 3, marginTop: 6, background: palette.accent, borderRadius: 2, opacity: 0.9 }} />
    </div>
  );
}

// ============================================================
// Task sticky card
// ============================================================
function TaskStickyCard({
  task,
  laneColor,
  laneAccent,
  density,
  quietMode,
  agentSurface,
  highlight,
  draggingId,
  onDragStart,
  onDragEnd,
  onOpen,
}: {
  task: BoardListCard;
  laneColor: string;
  laneAccent: string;
  density: 'cozy' | 'compact';
  quietMode: boolean;
  agentSurface: boolean;
  highlight: Highlight | null;
  draggingId: string;
  onDragStart: (e: DragEvent, t: BoardListCard) => void;
  onDragEnd: () => void;
  onOpen: (t: BoardListCard) => void;
}) {
  const kind = kindStyle(task.kind);
  const cozy = density === 'cozy';

  let isHighlighted = !highlight;
  if (highlight) {
    if (highlight.type === 'kind') isHighlighted = task.kind === highlight.value;
    else if (highlight.type === 'swim') isHighlighted = task.swimlane === highlight.value;
    else if (highlight.type === 'priority') isHighlighted = task.priority === highlight.value;
  }
  const dimmed = highlight != null && !isHighlighted;
  const isDragging = draggingId === task.id;

  // Card body colour = swimlane (domain). Kind is conveyed by the chip
  // next to TASK-ID, not the body — so "all Graph OS cards look green, all
  // Core cards look gray, regardless of whether they're bugs or features."
  const bg = quietMode
    ? 'linear-gradient(155deg, var(--board) 0%, var(--col-bg) 100%)'
    : `linear-gradient(155deg, ${alpha(laneColor, 0.16)} 0%, ${alpha(laneColor, 0.07)} 100%)`;

  const agentId = task.agent_session ? agentForSession(task.agent_session) : null;

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, task)}
      onDragEnd={onDragEnd}
      onClick={() => onOpen(task)}
      className="sticky-card"
      style={{
        position: 'relative',
        padding: cozy ? '10px 11px 9px' : '7px 9px 6px',
        margin: cozy ? '0 0 10px' : '0 0 6px',
        fontFamily: 'inherit',
        fontSize: cozy ? 14 : 12.5,
        lineHeight: 1.25,
        color: 'var(--cos-text)',
        background: bg,
        borderRadius: '8px',
        transform: 'none',
        boxShadow: isDragging
          ? '0 18px 26px rgba(0,0,0,.25), 0 3px 6px rgba(0,0,0,.18)'
          : dimmed
            ? '0 1px 2px rgba(0,0,0,.08)'
            : '0 2px 4px rgba(0,0,0,.12), 0 6px 10px -6px rgba(0,0,0,.18)',
        cursor: 'grab',
        transition: 'transform .15s ease, box-shadow .15s ease, opacity .15s ease, filter .15s ease',
        opacity: isDragging ? 0.4 : dimmed ? 0.22 : 1,
        filter: dimmed ? 'grayscale(0.7)' : 'none',
        borderLeft: `5px solid ${laneAccent || '#888'}`,
        overflow: 'hidden',
        ...priorityStyle(task.priority),
      }}
    >
      {quietMode && (
        <span
          style={{
            position: 'absolute',
            top: 6,
            right: 6,
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: kind.chip,
            boxShadow: '0 1px 2px rgba(0,0,0,.2)',
          }}
          title={kind.label}
        />
      )}
      {task.status === 'emergency' && (
        <div
          style={{
            position: 'absolute',
            width: 44,
            height: 18,
            top: -9,
            left: '50%',
            marginLeft: -22,
            background: 'linear-gradient(180deg, #ff6b6bdd 0%, #ff6b6baa 50%, #ff6b6bdd 100%)',
            transform: 'rotate(-6deg)',
            boxShadow: '0 1px 2px rgba(0,0,0,.15)',
            borderLeft: '1px dashed rgba(0,0,0,.08)',
            borderRight: '1px dashed rgba(0,0,0,.08)',
          }}
        />
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: cozy ? 4 : 2 }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: cozy ? 10 : 9,
            fontWeight: 700,
            color: 'var(--cos-muted)',
            letterSpacing: '.02em',
          }}
        >
          {task.id}
        </span>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
            fontWeight: 700,
            color: kind.chip,
            background: `color-mix(in oklab, ${kind.chip} 20%, transparent)`,
            border: `1px solid color-mix(in oklab, ${kind.chip} 38%, transparent)`,
            padding: '1px 5px',
            borderRadius: 3,
            letterSpacing: '.04em',
            textTransform: 'uppercase',
          }}
        >
          {kind.label}
        </span>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
            fontWeight: 700,
            color:
              task.priority === 'P0'
                ? 'var(--cos-err)'
                : task.priority === 'P1'
                  ? 'var(--cos-warn)'
                  : 'var(--cos-muted)',
          }}
        >
          {task.priority}
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 3, alignItems: 'center' }}>
          {agentId && agentSurface && <AgentPip agentId={agentId} />}
        </span>
      </div>

      <div
        style={{
          fontWeight: 700,
          fontSize: cozy ? 15 : 13.5,
          color: 'var(--cos-text)',
          whiteSpace: 'normal',
          overflowWrap: 'anywhere',
          wordBreak: 'break-word',
          hyphens: 'auto',
          maxWidth: '100%',
          marginBottom: cozy ? 6 : 3,
          fontFamily: 'inherit',
        }}
      >
        {task.title}
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 4,
          alignItems: 'center',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9,
          color: 'var(--cos-muted)',
          marginBottom: cozy && task.last_log_line ? 5 : 0,
        }}
      >
        <span style={{ background: 'var(--cos-inset)', padding: '1px 5px', borderRadius: 2 }}>
          ◷ {task.appetite || '1d'}
        </span>
        {task.epic && (
          <span style={{ background: 'var(--cos-inset)', padding: '1px 5px', borderRadius: 2, fontWeight: 600 }}>
            #{task.epic}
          </span>
        )}
        {task.status === 'icebox' && (task.labels || []).includes('ready') && (
          <span
            title="Tagged ready — candidate for pickup"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 3,
              background: 'linear-gradient(180deg, #86efac 0%, #4ade80 100%)',
              color: '#14532d',
              padding: '1px 6px',
              borderRadius: 10,
              fontWeight: 800,
              letterSpacing: '.04em',
              textTransform: 'uppercase',
              border: '1px solid #16a34a',
              boxShadow: '0 1px 1px rgba(22,163,74,.25)',
            }}
          >
            ● READY
          </span>
        )}
        {(task.labels || [])
          .filter((l) => l !== 'ready')
          .slice(0, cozy ? 3 : 2)
          .map((l) => (
            <span key={l} style={{ color: 'var(--cos-faint)', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
              ·{l}
            </span>
          ))}
      </div>

      {agentSurface && cozy && task.last_log_line && (
        <div
          style={{
            marginTop: 6,
            paddingTop: 5,
            borderTop: '1px dashed var(--cos-border)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9.5,
            color: 'var(--cos-muted)',
            lineHeight: 1.35,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          ↳ {task.last_log_line.replace(/^\d{4}-\d{2}-\d{2} \[[^\]]+\]:\s*/, '')}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Live stream panel
// ============================================================
function LiveStreamPanel({
  open,
  onClose,
  events,
  connected,
}: {
  open: boolean;
  onClose: () => void;
  events: BoardEvent[];
  connected: boolean;
}) {
  if (!open) return null;
  return (
    <div
      style={{
        position: 'fixed',
        top: 110,
        right: 14,
        bottom: 14,
        width: 380,
        zIndex: 50,
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 6,
        boxShadow: '0 20px 40px -10px rgba(0,0,0,.3)',
        display: 'flex',
        flexDirection: 'column',
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 12px',
          borderBottom: '1px solid var(--col-border)',
        }}
      >
        <div
          style={{
            fontFamily: 'inherit',
            fontSize: 14,
            letterSpacing: '.04em',
            color: 'var(--accent)',
          }}
        >
          AGENT STREAM
        </div>
        <span style={{ fontSize: 10, color: 'var(--ink-faint)' }}>
          <span
            style={{
              display: 'inline-block',
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: connected ? 'var(--cos-ok)' : 'var(--cos-err)',
              marginRight: 4,
              animation: connected ? 'pulse 1.5s infinite' : 'none',
            }}
          />
          {connected ? 'sse online' : 'sse offline'}
        </span>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--ink-faint)',
            cursor: 'pointer',
            fontSize: 16,
            lineHeight: 1,
            padding: 0,
          }}
        >
          ×
        </button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 4px' }}>
        {events.length === 0 && (
          <div
            style={{
              padding: '24px 14px',
              fontSize: 11,
              color: 'var(--ink-faint)',
              textAlign: 'center',
              lineHeight: 1.5,
            }}
          >
            waiting for events…
            <br />
            (drag a card or let agents touch docs/tasks/*.md)
          </div>
        )}
        {events.map((ev) => {
          const color = EVENT_COLOR[ev.kind] || 'var(--ink-soft)';
          const label = EVENT_LABEL[ev.kind] || ev.kind;
          // "Where is the task NOW?" chip — shown when the transition
          // is historical and the board column no longer reflects it.
          // Suppressed when new_status equals current_status (live row)
          // so the latest event doesn't render redundant noise like
          // `in_progress -> complete   now: complete`.
          const current = ev.currentStatus;
          const showCurrent = Boolean(current) && current !== ev.newStatus;
          return (
            <div
              key={ev.id}
              style={{
                padding: '6px 10px',
                borderBottom: '1px dotted var(--col-border)',
                fontSize: 10.5,
                lineHeight: 1.4,
                display: 'flex',
                gap: 6,
                alignItems: 'flex-start',
              }}
            >
              <span
                style={{ color: 'var(--ink-faint)', flexShrink: 0 }}
                title={ev.transitionedAt ? new Date(ev.transitionedAt * 1000).toLocaleString() : undefined}
              >
                {ev.t}
              </span>
              <AgentPip agentId={ev.agent} />
              <span
                style={{
                  color,
                  fontWeight: 700,
                  fontSize: 9,
                  flexShrink: 0,
                  padding: '1px 4px',
                  background: `${color}18`,
                  borderRadius: 2,
                  textTransform: 'uppercase',
                  letterSpacing: '.04em',
                }}
              >
                {label}
              </span>
              <div style={{ flex: 1, minWidth: 0, color: 'var(--ink)' }}>
                {ev.taskId && (
                  <span style={{ color: 'var(--accent)', fontWeight: 600, marginRight: 4 }}>
                    {ev.taskId}
                  </span>
                )}
                <span style={{ color: 'var(--ink-soft)' }}>{ev.message}</span>
                {showCurrent && (
                  <span
                    title="Current status in DB (the history event may be older than this)"
                    style={{
                      marginLeft: 6,
                      padding: '1px 5px',
                      borderRadius: 3,
                      fontSize: 9,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '.04em',
                      color: 'var(--ink-soft)',
                      background: 'var(--board-grain)',
                      border: '1px solid var(--col-border)',
                    }}
                  >
                    now: {current}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div
        style={{
          padding: '8px 12px',
          borderTop: '1px solid var(--col-border)',
          fontSize: 10,
          color: 'var(--ink-faint)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>agent file-watch · human drag/create</span>
        <span>{events.length} events</span>
      </div>
    </div>
  );
}

// ============================================================
// Tweaks panel
// ============================================================
function TweaksPanel({
  open,
  onClose,
  tweaks,
  setTweaks,
  kindOptions,
  epicOptions,
}: {
  open: boolean;
  onClose: () => void;
  tweaks: BoardTweaks;
  setTweaks: (updater: (prev: BoardTweaks) => BoardTweaks) => void;
  kindOptions: { value: string; label: string }[];
  epicOptions: { value: string; label: string }[];
}) {
  if (!open) return null;
  const set = <K extends keyof BoardTweaks>(k: K, v: BoardTweaks[K]) => setTweaks((t) => ({ ...t, [k]: v }));
  return (
    <div
      style={{
        position: 'fixed',
        bottom: 16,
        right: 16,
        zIndex: 100,
        width: 280,
        maxHeight: 'calc(100vh - 40px)',
        overflowY: 'auto',
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 6,
        boxShadow: '0 20px 40px -10px rgba(0,0,0,.3), 0 6px 12px rgba(0,0,0,.15)',
        fontFamily: "'Inter', sans-serif",
        color: 'var(--ink)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 12px 8px',
          borderBottom: '1px solid var(--col-border)',
        }}
      >
        <div
          style={{
            fontFamily: 'inherit',
            fontSize: 15,
            letterSpacing: '.04em',
            color: 'var(--accent)',
          }}
        >
          TWEAKS
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--ink-faint)',
            cursor: 'pointer',
            fontSize: 16,
            padding: 0,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </div>
      <div style={{ padding: '6px 10px 12px' }}>
        <Seg
          label="Theme"
          value={tweaks.theme}
          options={[
            { value: 'light', label: 'Light' },
            { value: 'dark', label: 'Dark' },
          ]}
          onChange={(v) => set('theme', v as BoardTweaks['theme'])}
        />
        <Seg
          label="Aesthetic"
          value={tweaks.aesthetic}
          options={[
            { value: 'whiteboard', label: 'Whiteboard' },
            { value: 'graph', label: 'Graph paper' },
            { value: 'terminal', label: 'Terminal' },
          ]}
          onChange={(v) => set('aesthetic', v as BoardTweaks['aesthetic'])}
        />
        <Seg
          label="Density"
          value={tweaks.density}
          options={[
            { value: 'cozy', label: 'Cozy' },
            { value: 'compact', label: 'Compact' },
          ]}
          onChange={(v) => set('density', v as BoardTweaks['density'])}
        />
        <div style={{ height: 1, background: 'var(--col-border)', margin: '6px 4px' }} />
        <Toggle on={tweaks.quietMode} onChange={(v) => set('quietMode', v)} label="Quiet mode" sub="subdued cards + kind as corner dot" />
        <Toggle on={tweaks.agentSurface} onChange={(v) => set('agentSurface', v)} label="Agent surface" sub="pips, work log stream, hook events" />
        <Toggle on={tweaks.showWipViolation} onChange={(v) => set('showWipViolation', v)} label="WIP violation state" sub="column flashes red when over cap" />
        <Toggle on={tweaks.showArchive} onChange={(v) => set('showArchive', v)} label="Show archive column" sub="soft-terminal cold store — hidden by default" />
        <div style={{ height: 1, background: 'var(--col-border)', margin: '6px 4px' }} />
        <Seg label="Filter — kind" value={tweaks.filterKind} options={kindOptions} onChange={(v) => set('filterKind', v)} />
        <Seg label="Filter — epic" value={tweaks.filterEpic} options={epicOptions} onChange={(v) => set('filterEpic', v)} />
      </div>
    </div>
  );
}

function Seg({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <div style={{ padding: '7px 4px' }}>
      <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginBottom: 5, fontWeight: 500 }}>{label}</div>
      <div style={{ display: 'flex', gap: 2, background: 'rgba(0,0,0,.08)', padding: 2, borderRadius: 5, flexWrap: 'wrap' }}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            style={{
              flex: '1 0 auto',
              padding: '5px 8px',
              fontSize: 11,
              fontFamily: "'Inter', sans-serif",
              fontWeight: 500,
              background: value === o.value ? 'var(--board)' : 'transparent',
              color: value === o.value ? 'var(--ink)' : 'var(--ink-soft)',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              boxShadow: value === o.value ? '0 1px 2px rgba(0,0,0,.1)' : 'none',
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({
  on,
  onChange,
  label,
  sub,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  label: string;
  sub?: string;
}) {
  return (
    <label
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '7px 4px',
        cursor: 'pointer',
        userSelect: 'none',
      }}
    >
      <div
        onClick={() => onChange(!on)}
        style={{
          width: 32,
          height: 18,
          borderRadius: 10,
          background: on ? 'var(--accent)' : 'rgba(0,0,0,.18)',
          position: 'relative',
          transition: 'background .15s ease',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: 2,
            left: on ? 16 : 2,
            width: 14,
            height: 14,
            borderRadius: '50%',
            background: 'white',
            transition: 'left .15s ease',
            boxShadow: '0 1px 2px rgba(0,0,0,.2)',
          }}
        />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>{label}</div>
        {sub && <div style={{ fontSize: 10, color: 'var(--ink-faint)', marginTop: 1 }}>{sub}</div>}
      </div>
    </label>
  );
}

// ============================================================
// Legend panel
// ============================================================
function LegendPanel({
  open,
  onClose,
  swimlanes,
  filterKind,
  setFilterKind,
  filterSwim,
  setFilterSwim,
  highlight,
  setHighlight,
  taskCounts,
}: {
  open: boolean;
  onClose: () => void;
  swimlanes: SwimlaneDTO[];
  filterKind: string;
  setFilterKind: (v: string) => void;
  filterSwim: string;
  setFilterSwim: (v: string) => void;
  highlight: Highlight | null;
  setHighlight: (h: Highlight | null) => void;
  taskCounts: TaskCounts;
}) {
  // Hook must run unconditionally — call before the early return (rules-of-hooks).
  const legendAgents = useAgentCatalog();
  if (!open) return null;
  const kinds = Object.entries(KIND_COLORS);
  return (
    <div
      style={{
        position: 'fixed',
        top: 110,
        right: 14,
        bottom: 14,
        zIndex: 50,
        width: 280,
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 6,
        boxShadow: '0 20px 40px -10px rgba(0,0,0,.3)',
        fontFamily: "'Inter', sans-serif",
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          borderBottom: '1px solid var(--col-border)',
        }}
      >
        <div
          style={{
            fontFamily: 'inherit',
            fontSize: 13,
            letterSpacing: '.04em',
            color: 'var(--accent)',
          }}
        >
          LEGEND
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--ink-faint)',
            cursor: 'pointer',
            fontSize: 14,
            lineHeight: 1,
            padding: 0,
          }}
        >
          ×
        </button>
      </div>

      <div style={{ padding: 10 }}>
        <LegendSection title="Kind — card body">
          {kinds.map(([k, v]) => {
            const active = filterKind === k || (highlight?.type === 'kind' && highlight?.value === k);
            const dim =
              (filterKind !== 'all' && filterKind !== k) ||
              (highlight?.type === 'kind' && highlight?.value !== k);
            return (
              <LegendRow
                key={k}
                swatch={
                  <span
                    style={{
                      display: 'inline-block',
                      width: 14,
                      height: 14,
                      background: `linear-gradient(155deg, ${v.bg} 0%, ${v.bg2} 100%)`,
                      border: `1px solid ${v.chip}`,
                      borderRadius: 2,
                    }}
                  />
                }
                label={v.label}
                sub={String(taskCounts.kind[k] || 0)}
                active={!!active}
                dim={!!dim}
                onEnter={() => setHighlight({ type: 'kind', value: k })}
                onLeave={() => setHighlight(null)}
                onClick={() => setFilterKind(filterKind === k ? 'all' : k)}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Swimlane — left band">
          {swimlanes.map((lane) => {
            const p = lanePalette(lane);
            const active = filterSwim === lane.id || (highlight?.type === 'swim' && highlight?.value === lane.id);
            const dim =
              (filterSwim !== 'all' && filterSwim !== lane.id) ||
              (highlight?.type === 'swim' && highlight?.value !== lane.id);
            return (
              <LegendRow
                key={lane.id}
                swatch={
                  <span
                    style={{
                      width: 14,
                      height: 14,
                      background: alpha(p.color, 0.3),
                      borderLeft: `4px solid ${p.accent}`,
                      border: '1px solid rgba(0,0,0,.15)',
                      display: 'inline-block',
                    }}
                  />
                }
                label={lane.label}
                sub={String(taskCounts.swim[lane.id] || 0)}
                active={!!active}
                dim={!!dim}
                onEnter={() => setHighlight({ type: 'swim', value: lane.id })}
                onLeave={() => setHighlight(null)}
                onClick={() => setFilterSwim(filterSwim === lane.id ? 'all' : lane.id)}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Priority — outline">
          {[
            { id: 'P0', label: 'P0 · critical', style: { outline: '2.5px double #c0392b', outlineOffset: 1 } as CSSProperties },
            { id: 'P1', label: 'P1 · high', style: { outline: '1.5px solid #ea580c' } as CSSProperties },
            { id: 'P2', label: 'P2 · normal', style: { outline: '1px dashed #8a8378' } as CSSProperties },
            { id: 'P3', label: 'P3 · low', style: { outline: '1px dotted #b8b0a3' } as CSSProperties },
          ].map((p) => {
            const active = highlight?.type === 'priority' && highlight?.value === p.id;
            const dim = highlight?.type === 'priority' && highlight?.value !== p.id;
            return (
              <LegendRow
                key={p.id}
                swatch={
                  <span
                    style={{
                      width: 16,
                      height: 12,
                      background: 'rgba(0,0,0,.04)',
                      ...p.style,
                      display: 'inline-block',
                    }}
                  />
                }
                label={p.label}
                sub={String(taskCounts.priority[p.id] || 0)}
                active={!!active}
                dim={!!dim}
                onEnter={() => setHighlight({ type: 'priority', value: p.id })}
                onLeave={() => setHighlight(null)}
                onClick={() => {}}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Agent — corner pip">
          <div style={{ display: 'flex', gap: 8, padding: '3px 5px', flexWrap: 'wrap' }}>
            {legendAgents.map((a) => (
              <div
                key={a.id}
                style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--ink)' }}
              >
                <AgentBadge agentId={a.id} state="active" />
              </div>
            ))}
          </div>
        </LegendSection>
      </div>
    </div>
  );
}

function LegendSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9,
          fontWeight: 700,
          color: 'var(--ink-faint)',
          letterSpacing: '.08em',
          textTransform: 'uppercase',
          marginBottom: 5,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function LegendRow({
  swatch,
  label,
  sub,
  active,
  dim,
  onEnter,
  onLeave,
  onClick,
}: {
  swatch: ReactNode;
  label: string;
  sub?: string;
  active: boolean;
  dim: boolean;
  onEnter: () => void;
  onLeave: () => void;
  onClick: () => void;
}) {
  return (
    <div
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        padding: '3px 5px',
        fontFamily: "'Inter', sans-serif",
        fontSize: 11,
        color: dim ? 'var(--ink-faint)' : 'var(--ink)',
        cursor: 'pointer',
        borderRadius: 3,
        background: active ? 'rgba(217, 108, 44, .15)' : 'transparent',
        opacity: dim ? 0.4 : 1,
        transition: 'opacity .1s ease, background .1s ease',
        userSelect: 'none',
      }}
    >
      {swatch}
      <span style={{ fontWeight: active ? 700 : 500 }}>{label}</span>
      {sub && <span style={{ color: 'var(--ink-faint)', fontSize: 10, marginLeft: 'auto' }}>{sub}</span>}
    </div>
  );
}

// ============================================================
// Zoom controls
// ============================================================
function ZoomControls({
  zoom,
  setZoom,
  collapsedCount,
  onExpandAll,
  onCollapseEmpty,
}: {
  zoom: number;
  setZoom: (v: number) => void;
  collapsedCount: number;
  onExpandAll: () => void;
  onCollapseEmpty: () => void;
}) {
  const pct = Math.round(zoom * 100);
  return (
    <div
      style={{
        position: 'fixed',
        right: 20,
        bottom: 20,
        zIndex: 45,
        display: 'flex',
        alignItems: 'stretch',
        gap: 6,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 4,
          boxShadow: '0 4px 14px rgba(0,0,0,.12)',
          overflow: 'hidden',
        }}
      >
        <ZoomBtn onClick={onCollapseEmpty} title="Collapse empty lanes">
          ⊟ empty
        </ZoomBtn>
        <ZoomDiv />
        <ZoomBtn onClick={onExpandAll} disabled={collapsedCount === 0} title="Expand all">
          ⊞ expand
        </ZoomBtn>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 4,
          boxShadow: '0 4px 14px rgba(0,0,0,.12)',
          overflow: 'hidden',
        }}
      >
        <ZoomBtn onClick={() => setZoom(zoom - 0.1)} disabled={zoom <= 0.5} title="Zoom out (⌘-)">
          −
        </ZoomBtn>
        <ZoomDiv />
        <button
          type="button"
          onClick={() => setZoom(1)}
          title="Reset (⌘0)"
          style={{
            padding: '0 10px',
            minWidth: 54,
            height: 30,
            background: 'transparent',
            border: 'none',
            color: pct === 100 ? 'var(--ink-faint)' : 'var(--accent)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          {pct}%
        </button>
        <ZoomDiv />
        <ZoomBtn onClick={() => setZoom(zoom + 0.1)} disabled={zoom >= 1.5} title="Zoom in (⌘+)">
          +
        </ZoomBtn>
        <ZoomDiv />
        <input
          type="range"
          min={0.5}
          max={1.5}
          step={0.05}
          value={zoom}
          onChange={(e) => setZoom(parseFloat(e.target.value))}
          style={{ width: 90, margin: '0 10px', accentColor: 'var(--accent)' }}
        />
      </div>
    </div>
  );
}

function ZoomBtn({
  children,
  onClick,
  disabled,
  title,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        height: 30,
        minWidth: 30,
        padding: '0 9px',
        background: 'transparent',
        border: 'none',
        color: disabled ? 'var(--ink-faint)' : 'var(--ink)',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 13,
        fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.35 : 1,
      }}
    >
      {children}
    </button>
  );
}

function ZoomDiv() {
  return <div style={{ width: 1, background: 'var(--col-border)', alignSelf: 'stretch' }} />;
}

// ============================================================
// Create task modal
// ============================================================
function CreateTaskModal({
  open,
  onClose,
  nextId,
  swimlanes,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  nextId: number;
  swimlanes: SwimlaneDTO[];
  onCreate: (form: CreateTaskForm) => Promise<void>;
}) {
  const [form, setForm] = useState<{
    title: string;
    swimlane: string;
    kind: string;
    priority: string;
    appetite: string;
    epic: string;
    labels: string;
    outcome: string;
  }>({
    title: '',
    swimlane: '',
    kind: 'feature',
    priority: 'P2',
    appetite: '1d',
    epic: '',
    labels: '',
    outcome: '',
  });

  useEffect(() => {
    if (open) {
      setForm({
        title: '',
        swimlane: swimlanes[0]?.id || '',
        kind: 'feature',
        priority: 'P2',
        appetite: '1d',
        epic: '',
        labels: '',
        outcome: '',
      });
    }
  }, [open, swimlanes]);

  if (!open) return null;

  const kindOpts = Object.entries(KIND_COLORS).map(([k, v]) => ({
    value: k,
    label: v.label,
    color: v.chip,
  }));
  const priorityOpts = [
    { value: 'P0', label: 'P0', color: 'var(--cos-err)' },
    { value: 'P1', label: 'P1', color: 'var(--cos-warn)' },
    { value: 'P2', label: 'P2', color: 'var(--cos-muted)' },
    { value: 'P3', label: 'P3', color: 'var(--cos-faint)' },
  ];
  const previewKind = kindStyle(form.kind);
  const previewLane = swimlanes.find((l) => l.id === form.swimlane);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        background: 'rgba(0,0,0,.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
        animation: 'fadeIn .15s ease',
      }}
      onClick={onClose}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault();
          if (!form.title.trim() || !form.swimlane) return;
          await onCreate({
            title: form.title.trim(),
            swimlane: form.swimlane,
            kind: form.kind,
            priority: form.priority,
            appetite: form.appetite,
            epic: form.epic || null,
            labels: form.labels.split(',').map((s) => s.trim()).filter(Boolean),
            outcome: form.outcome || null,
          });
        }}
        style={{
          width: 720,
          maxWidth: '100%',
          maxHeight: '90vh',
          overflowY: 'auto',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 6,
          boxShadow: '0 30px 60px rgba(0,0,0,.4)',
          display: 'grid',
          gridTemplateColumns: '1fr 240px',
        }}
      >
        <div style={{ padding: '20px 22px', borderRight: '1px solid var(--col-border)' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 10,
              marginBottom: 18,
              paddingBottom: 10,
              borderBottom: '2px dashed var(--col-border)',
            }}
          >
            <div
              style={{
                fontFamily: 'inherit',
                fontSize: 22,
                letterSpacing: '.02em',
                color: 'var(--accent)',
              }}
            >
              new task
            </div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: 'var(--ink-faint)' }}>
              cos_task_create → TASK-{String(nextId).padStart(3, '0')}
            </div>
          </div>

          <FormField label="Title" required>
            <input
              autoFocus
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="Implement Kuzu backend"
              maxLength={80}
              style={formInput}
            />
          </FormField>

          <FormField label="Swimlane" required>
            <ChipRow
              options={swimlanes.map((s) => ({ value: s.id, label: s.label, color: s.accent }))}
              value={form.swimlane}
              onChange={(v) => setForm((f) => ({ ...f, swimlane: v }))}
            />
          </FormField>

          <FormField label="Kind" required>
            <ChipRow options={kindOpts} value={form.kind} onChange={(v) => setForm((f) => ({ ...f, kind: v }))} />
          </FormField>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <FormField label="Priority" required>
              <ChipRow options={priorityOpts} value={form.priority} onChange={(v) => setForm((f) => ({ ...f, priority: v }))} />
            </FormField>
            <FormField label="Appetite" required hint="30m 2h 1d 3d 1w">
              <input
                value={form.appetite}
                onChange={(e) => setForm((f) => ({ ...f, appetite: e.target.value }))}
                style={monoFormInput}
              />
            </FormField>
          </div>

          <FormField label="Labels" hint="comma-separated">
            <input
              value={form.labels}
              onChange={(e) => setForm((f) => ({ ...f, labels: e.target.value }))}
              placeholder="indexing, perf"
              style={monoFormInput}
            />
          </FormField>

          <FormField label="Outcome / first work-log line" hint="optional">
            <textarea
              value={form.outcome}
              onChange={(e) => setForm((f) => ({ ...f, outcome: e.target.value }))}
              rows={2}
              style={{ ...formInput, resize: 'vertical' }}
            />
          </FormField>

          <div
            style={{
              display: 'flex',
              gap: 10,
              justifyContent: 'flex-end',
              marginTop: 14,
              paddingTop: 14,
              borderTop: '1px dashed var(--col-border)',
            }}
          >
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '8px 14px',
                fontSize: 12,
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 600,
                background: 'transparent',
                color: 'var(--ink-soft)',
                border: '1.5px solid var(--col-border)',
                borderRadius: 3,
                cursor: 'pointer',
              }}
            >
              cancel
            </button>
            <button
              type="submit"
              style={{
                padding: '8px 18px',
                fontSize: 12,
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 700,
                background: 'var(--accent)',
                color: 'white',
                border: '1.5px solid var(--accent)',
                borderRadius: 3,
                cursor: 'pointer',
                letterSpacing: '.02em',
              }}
            >
              create ▸
            </button>
          </div>
        </div>

        <div
          style={{
            padding: '20px 18px',
            background: 'var(--board)',
            borderRadius: '0 6px 6px 0',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 10,
              fontWeight: 600,
              color: 'var(--ink-soft)',
              letterSpacing: '.04em',
              textTransform: 'uppercase',
              marginBottom: 10,
            }}
          >
            preview
          </div>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div
              style={{
                width: 200,
                padding: '10px 11px 9px',
                fontFamily: 'inherit',
                fontSize: 14,
                lineHeight: 1.25,
                color: 'var(--cos-text)',
                background: previewLane
                  ? `linear-gradient(155deg, ${alpha(previewLane.color, 0.16)} 0%, ${alpha(previewLane.color, 0.07)} 100%)`
                  : 'linear-gradient(155deg, var(--cos-raised) 0%, var(--cos-panel) 100%)',
                borderRadius: '8px',
                transform: 'none',
                boxShadow: '0 4px 8px rgba(0,0,0,.15), 0 10px 20px -6px rgba(0,0,0,.2)',
                borderLeft: `5px solid ${previewLane ? lanePalette(previewLane).accent : '#888'}`,
                ...priorityStyle(form.priority),
              }}
            >
              <div style={{ display: 'flex', gap: 6, marginBottom: 4, alignItems: 'center' }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fontWeight: 700 }}>
                  TASK-{String(nextId).padStart(3, '0')}
                </span>
                <span
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 9,
                    fontWeight: 700,
                    color: '#fff',
                    background: previewKind.chip,
                    padding: '1px 5px',
                    borderRadius: 2,
                    textTransform: 'uppercase',
                  }}
                >
                  {previewKind.label}
                </span>
              </div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>
                {form.title || <span style={{ color: '#9a948a', fontStyle: 'italic' }}>(title…)</span>}
              </div>
            </div>
          </div>
          <div
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 10,
              color: 'var(--ink-faint)',
              marginTop: 12,
              lineHeight: 1.5,
            }}
          >
            → docs/tasks/TASK-{String(nextId).padStart(3, '0')}-
            {(form.title || 'untitled').toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 30)}.md
            <br />→ lane <b style={{ color: previewLane?.accent }}>{form.swimlane || '…'}</b>
          </div>
        </div>
      </form>
    </div>
  );
}

const formInput: CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  fontFamily: 'inherit',
  fontSize: 15,
  background: 'var(--board)',
  color: 'var(--ink)',
  border: '1.5px solid var(--col-border)',
  borderRadius: 3,
  outline: 'none',
};
const monoFormInput: CSSProperties = {
  ...formInput,
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12,
};

function FormField({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 10,
          fontWeight: 600,
          color: 'var(--ink-soft)',
          letterSpacing: '.04em',
          textTransform: 'uppercase',
          marginBottom: 4,
        }}
      >
        {label}
        {required && <span style={{ color: '#c0392b' }}> *</span>}
        {hint && (
          <span style={{ color: 'var(--ink-faint)', fontWeight: 400, textTransform: 'none', marginLeft: 6 }}>
            — {hint}
          </span>
        )}
      </div>
      {children}
    </label>
  );
}

function ChipRow({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string; color?: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          style={{
            padding: '5px 9px',
            fontSize: 11,
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 600,
            background: value === o.value ? o.color || 'var(--accent)' : 'transparent',
            color: value === o.value ? 'white' : 'var(--ink-soft)',
            border: `1.5px solid ${value === o.value ? o.color || 'var(--accent)' : 'var(--col-border)'}`,
            borderRadius: 3,
            cursor: 'pointer',
            transition: 'all .12s ease',
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ============================================================
// Task detail drawer — fetches docs/tasks/TASK-NNN-*.md from the
// backend and renders it with the md-body typography defined in
// cos-board-tokens.css (matches the Claude Design prototype).
// ============================================================

interface TaskDetailPayload {
  task_id: string;
  file_path: string;
  exists: boolean;
  content: string;
  size: number;
  mtime: number;
  truncated: boolean;
  row: {
    title: string;
    status: string;
    swimlane: string;
    kind: string;
    priority: string;
    appetite: string;
    epic: string | null;
    labels: string[];
  };
}

interface TaskEditFormState {
  title: string;
  priority: string;
  swimlane: string;
  appetite: string;
  labels: string;
  body: string;
}

function TaskDetailDrawer({
  task,
  swimlanes,
  onClose,
}: {
  task: BoardListCard | null;
  swimlanes: SwimlaneDTO[];
  onClose: () => void;
}) {
  const laneColorFor = (swimId: string): string | undefined =>
    swimlanes.find((s) => s.id === swimId)?.color;
  const queryKey = useMemo(() => ['board-task', task?.id ?? ''], [task?.id]);
  const { data, isLoading, error } = useApiGet<TaskDetailPayload>(
    queryKey,
    task ? `/api/board/task/${task.id}` : '/api/board/task/__noop__',
    undefined,
    { enabled: !!task },
  );

  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [form, setForm] = useState<TaskEditFormState | null>(null);

  useEffect(() => {
    if (!task) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [task, onClose]);

  if (!task) return null;

  const meta = data?.row;
  const kindRaw = meta?.kind ?? task.kind;
  const kind = kindStyle(kindRaw);
  const status = (meta?.status ?? task.status).toUpperCase();
  const swimlane = meta?.swimlane ?? task.swimlane;
  const priority = meta?.priority ?? task.priority;
  const appetite = meta?.appetite ?? task.appetite ?? '1d';
  const epic = meta?.epic ?? task.epic ?? null;
  const labels = meta?.labels ?? task.labels ?? [];
  const title = meta?.title ?? task.title;
  const filePath = data?.file_path || `docs/tasks/${task.id}-...md`;

  // Priority colour — mirrors task_detail.jsx prototype palette.
  const priorityColor: Record<string, string> = {
    P0: '#dc2626',
    P1: '#ea580c',
    P2: '#ca8a04',
    P3: '#64748b',
  };
  const priColor = priorityColor[priority] ?? 'var(--ink)';

  // Strip YAML frontmatter + leading H1 (drawer header already shows title).
  let body = '';
  if (data?.content) {
    const split = splitFrontmatter(data.content);
    body = split.body.replace(/^\s*#\s+.+\n+/, '');
  }

  const isReady = labels.includes('ready');
  const refresh = () => {
    void invalidateApiQueries(qc, '/api/board/list');
    void invalidateApiQueries(qc, `/api/board/task/${task.id}`);
    void invalidateApiQueries(qc, `/api/board/task/${task.id}/history`);
  };
  const enterEdit = () => {
    setForm({ title, priority, swimlane, appetite, labels: labels.join(', '), body });
    setSaveErr(null);
    setEditing(true);
  };
  const cancelEdit = () => {
    setEditing(false);
    setForm(null);
  };
  const saveEdit = async () => {
    if (!form) return;
    setSaving(true);
    setSaveErr(null);
    try {
      await apiPatch(`/api/board/task/${task.id}`, {
        title: form.title,
        priority: form.priority,
        swimlane: form.swimlane,
        appetite: form.appetite,
        labels: form.labels.split(',').map((s) => s.trim()).filter(Boolean),
        body: form.body,
      });
      refresh();
      setEditing(false);
      setForm(null);
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : 'save failed');
    } finally {
      setSaving(false);
    }
  };
  const toggleReady = async () => {
    try {
      await apiPost(`/api/board/task/${task.id}/ready`, { ready: !isReady });
      refresh();
    } catch {
      /* error surfaces on the next fetch */
    }
  };

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(10,12,16,.55)',
          backdropFilter: 'blur(3px)',
          WebkitBackdropFilter: 'blur(3px)',
          zIndex: 80,
          animation: 'td-fade-in 180ms ease',
        }}
      />
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: 'min(960px, 94vw)',
          background: 'var(--col-bg)',
          borderLeft: '1px solid var(--col-border)',
          boxShadow: '-30px 0 60px rgba(0,0,0,.3)',
          zIndex: 81,
          display: 'flex',
          flexDirection: 'column',
          animation: 'td-slide-in 220ms cubic-bezier(.22,.61,.36,1)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '14px 22px 14px',
            borderBottom: '1px solid var(--col-border)',
            background: 'linear-gradient(180deg, var(--col-bg) 0, var(--board-grain) 100%)',
            flex: '0 0 auto',
          }}
        >
          {/* file path + actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 11,
                color: 'var(--ink-faint)',
                letterSpacing: '.04em',
                flex: 1,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
              title={filePath}
            >
              <span style={{ color: 'var(--ink-soft)' }}>📄</span>
              {filePath}
              {data?.truncated && (
                <span
                  style={{
                    padding: '1px 5px',
                    fontSize: 9,
                    fontWeight: 700,
                    background: 'var(--cos-warn)',
                    color: 'white',
                    borderRadius: 2,
                    letterSpacing: '.04em',
                  }}
                >
                  TRUNC
                </span>
              )}
            </span>
            <button
              type="button"
              onClick={onClose}
              title="Close (esc)"
              style={{
                background: 'transparent',
                border: '1px solid var(--col-border)',
                color: 'var(--ink-soft)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 11,
                padding: '3px 10px',
                borderRadius: 3,
                cursor: 'pointer',
                letterSpacing: '.02em',
              }}
            >
              esc
            </button>
          </div>

          {/* title row: TASK-ID + kind chip + title */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
            <span
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 14,
                fontWeight: 700,
                color: 'var(--accent)',
                padding: '2px 7px',
                background: 'var(--board-grain)',
                border: '1px solid var(--col-border)',
                borderRadius: 3,
              }}
            >
              {task.id}
            </span>
            <h1
              style={{
                margin: 0,
                flex: 1,
                fontFamily: "'Inter', system-ui, sans-serif",
                fontSize: 22,
                fontWeight: 600,
                lineHeight: 1.25,
                color: 'var(--ink)',
                letterSpacing: '-.01em',
              }}
            >
              {title}
            </h1>
          </div>

          {/* metadata pills */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 6,
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11,
            }}
          >
            <Pill label="status" value={status} />
            <Pill label="swimlane" value={swimlane} dot={laneColorFor(swimlane)} />
            <Pill label="kind" value={kindRaw} dot={kind.chip} />
            <Pill label="priority" value={priority} valueColor={priColor} strong />
            <Pill label="appetite" value={appetite} />
            {epic && <Pill label="epic" value={`#${epic}`} />}
            {labels.map((l) => (
              <span
                key={l}
                style={{
                  fontSize: 10,
                  padding: '2px 7px',
                  background: 'transparent',
                  color: 'var(--ink-soft)',
                  border: '1px dashed var(--col-border)',
                  borderRadius: 10,
                }}
              >
                #{l}
              </span>
            ))}
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: 'auto', padding: '18px 28px 40px', background: 'var(--col-bg)' }}>
          {isLoading && (
            <div style={{ color: 'var(--ink-faint)', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
              loading {task.id}.md…
            </div>
          )}
          {error && !isLoading && (
            <div
              style={{
                padding: 12,
                border: '1px dashed rgba(220,38,38,.4)',
                background: 'rgba(220,38,38,.06)',
                color: 'var(--cos-err)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
                borderRadius: 4,
              }}
            >
              could not load task file — {error.message}
            </div>
          )}
          {data && !data.exists && !isLoading && !error && (
            <div
              style={{
                padding: 12,
                border: '1px dashed var(--col-border)',
                background: 'var(--board-grain)',
                color: 'var(--ink-faint)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
                borderRadius: 4,
              }}
            >
              no file on disk for this task — DB row only.
            </div>
          )}
          {editing && form ? (
            <TaskEditForm
              form={form}
              setForm={setForm}
              swimlanes={swimlanes}
              saving={saving}
              error={saveErr}
            />
          ) : (
            <>
              {data && data.exists && (
                <div className="md-body">{renderTaskMarkdown(body)}</div>
              )}
              <TaskHistoryPanel taskId={task.id} />
              <TaskTranscriptPanel taskId={task.id} />
            </>
          )}
        </div>

        {/* Footer — command hints from the prototype */}
        <div
          style={{
            flex: '0 0 auto',
            padding: '8px 16px',
            borderTop: '1px solid var(--col-border)',
            background: 'var(--board-grain)',
            display: 'flex',
            gap: 6,
            alignItems: 'center',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 10.5,
            color: 'var(--ink-faint)',
          }}
        >
          {editing ? (
            <>
              <button
                type="button"
                onClick={saveEdit}
                disabled={saving}
                style={{
                  background: 'var(--accent)',
                  border: '1px solid var(--accent)',
                  color: '#fff',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  padding: '3px 12px',
                  borderRadius: 3,
                  cursor: saving ? 'default' : 'pointer',
                  opacity: saving ? 0.6 : 1,
                }}
              >
                {saving ? 'saving…' : '✓ save'}
              </button>
              <button
                type="button"
                onClick={cancelEdit}
                disabled={saving}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--col-border)',
                  color: 'var(--ink-soft)',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  padding: '3px 12px',
                  borderRadius: 3,
                  cursor: 'pointer',
                }}
              >
                cancel
              </button>
              {saveErr && <span style={{ color: '#dc2626' }}>{saveErr}</span>}
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={enterEdit}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--col-border)',
                  color: 'var(--ink-soft)',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  padding: '3px 12px',
                  borderRadius: 3,
                  cursor: 'pointer',
                }}
              >
                ✎ edit
              </button>
              {status === 'ICEBOX' && (
                <button
                  type="button"
                  onClick={toggleReady}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--col-border)',
                    color: isReady ? 'var(--accent)' : 'var(--ink-soft)',
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11,
                    padding: '3px 12px',
                    borderRadius: 3,
                    cursor: 'pointer',
                  }}
                >
                  {isReady ? '✓ ready · unmark' : '○ mark ready'}
                </button>
              )}
            </>
          )}
          <span style={{ flex: 1 }} />
          <span style={{ opacity: 0.7 }}>esc close</span>
        </div>
      </div>
    </>
  );
}

function Pill({
  label,
  value,
  strong,
  dot,
  valueColor,
}: {
  label: string;
  value: string;
  strong?: boolean;
  dot?: string;
  valueColor?: string;
}) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 7px 2px 5px',
        background: 'var(--board-grain)',
        border: '1px solid var(--col-border)',
        borderRadius: 3,
      }}
    >
      {dot && <span style={{ width: 7, height: 7, borderRadius: 2, background: dot }} />}
      <span style={{ color: 'var(--ink-faint)' }}>{label}</span>
      <span style={{ color: valueColor ?? 'var(--ink)', fontWeight: strong ? 700 : 500 }}>{value}</span>
    </span>
  );
}

// ---------- Task history (create + status + edits + commits) ----------

interface TaskHistoryEvent {
  type: 'created' | 'status' | 'edit' | 'commit';
  at: number;
  actor?: { type: string; id: string; label: string };
  from?: string | null;
  to?: string;
  reason?: string | null;
  override_reason?: string | null;
  field?: string;
  sha?: string;
  subject?: string;
}

interface TaskHistoryPayload {
  task_id: string;
  events: TaskHistoryEvent[];
  summary: {
    created_by: string | null;
    created_at: number | null;
    last_edited_by: string | null;
    last_edited_at: number | null;
    contributors: string[];
    commit_count: number;
  };
  count: number;
}

const HISTORY_ICON: Record<TaskHistoryEvent['type'], string> = {
  created: '✦',
  status: '→',
  edit: '✎',
  commit: '⎇',
};

function TaskHistoryPanel({ taskId }: { taskId: string }) {
  const { data, isLoading } = useApiGet<TaskHistoryPayload>(
    ['board-task-history', taskId],
    `/api/board/task/${taskId}/history`,
    { include_commits: true },
    { enabled: !!taskId },
  );

  const baseFont = "'JetBrains Mono', monospace";
  if (isLoading) {
    return (
      <div style={{ marginTop: 24, fontFamily: baseFont, fontSize: 11, color: 'var(--ink-faint)' }}>
        loading history…
      </div>
    );
  }
  const events = data?.events ?? [];
  if (!events.length) return null;
  const s = data?.summary;
  const fmt = (at: number) => (at ? new Date(at * 1000).toLocaleString() : '');

  const describe = (e: TaskHistoryEvent): string => {
    const who = e.actor?.label ?? '—';
    if (e.type === 'created') return `created by ${who}`;
    if (e.type === 'status') {
      const reason = e.override_reason || e.reason;
      return `${e.from ?? ''} → ${e.to} · ${who}${reason ? ` (${reason})` : ''}`;
    }
    if (e.type === 'edit') return `edited ${e.field} · ${who}`;
    return `commit ${e.sha} · ${e.subject}`;
  };

  return (
    <div style={{ marginTop: 24, borderTop: '1px solid var(--col-border)', paddingTop: 14 }}>
      <div
        style={{
          fontFamily: baseFont,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '.08em',
          color: 'var(--ink-soft)',
          marginBottom: 8,
        }}
      >
        HISTORY
      </div>
      {s && (
        <div style={{ fontFamily: baseFont, fontSize: 11, color: 'var(--ink-faint)', marginBottom: 10 }}>
          created by {s.created_by ?? '—'}
          {s.last_edited_by ? ` · last edit by ${s.last_edited_by}` : ''}
          {s.contributors?.length ? ` · contributors: ${s.contributors.join(', ')}` : ''}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {events
          .slice()
          .reverse()
          .map((e, i) => (
            <div
              key={`${e.type}-${e.at}-${i}`}
              style={{ display: 'flex', gap: 8, fontFamily: baseFont, fontSize: 11, alignItems: 'baseline' }}
            >
              <span style={{ color: 'var(--accent)', width: 12, flex: '0 0 auto' }}>
                {HISTORY_ICON[e.type]}
              </span>
              <span style={{ color: 'var(--ink-faint)', minWidth: 132, flex: '0 0 auto' }}>{fmt(e.at)}</span>
              <span style={{ color: 'var(--ink)' }}>{describe(e)}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

// ---------- Task edit form (human-actor panel edit) ----------

function TaskEditForm({
  form,
  setForm,
  swimlanes,
  saving,
  error,
}: {
  form: TaskEditFormState;
  setForm: (value: TaskEditFormState | null) => void;
  swimlanes: SwimlaneDTO[];
  saving: boolean;
  error: string | null;
}) {
  const mono = "'JetBrains Mono', monospace";
  const set = (k: keyof TaskEditFormState, v: string) => setForm({ ...form, [k]: v });
  const inputStyle: CSSProperties = {
    width: '100%',
    background: 'var(--board-grain)',
    border: '1px solid var(--col-border)',
    color: 'var(--ink)',
    fontFamily: mono,
    fontSize: 12,
    padding: '6px 8px',
    borderRadius: 3,
  };
  const labelStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    fontFamily: mono,
    fontSize: 10.5,
    color: 'var(--ink-faint)',
    letterSpacing: '.04em',
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {error && <div style={{ color: '#dc2626', fontFamily: mono, fontSize: 12 }}>{error}</div>}
      <label style={labelStyle}>
        TITLE
        <input
          value={form.title}
          disabled={saving}
          onChange={(e) => set('title', e.target.value)}
          style={inputStyle}
        />
      </label>
      <div style={{ display: 'flex', gap: 12 }}>
        <label style={{ ...labelStyle, flex: 1 }}>
          PRIORITY
          <select
            value={form.priority}
            disabled={saving}
            onChange={(e) => set('priority', e.target.value)}
            style={inputStyle}
          >
            {['P0', 'P1', 'P2', 'P3'].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label style={{ ...labelStyle, flex: 2 }}>
          SWIMLANE
          <select
            value={form.swimlane}
            disabled={saving}
            onChange={(e) => set('swimlane', e.target.value)}
            style={inputStyle}
          >
            {swimlanes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label ?? s.id}
              </option>
            ))}
          </select>
        </label>
        <label style={{ ...labelStyle, flex: 1 }}>
          APPETITE
          <input
            value={form.appetite}
            disabled={saving}
            onChange={(e) => set('appetite', e.target.value)}
            style={inputStyle}
          />
        </label>
      </div>
      <label style={labelStyle}>
        LABELS (comma-separated)
        <input
          value={form.labels}
          disabled={saving}
          onChange={(e) => set('labels', e.target.value)}
          style={inputStyle}
        />
      </label>
      <label style={labelStyle}>
        BODY (markdown)
        <textarea
          value={form.body}
          disabled={saving}
          onChange={(e) => set('body', e.target.value)}
          rows={22}
          style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5 }}
        />
      </label>
    </div>
  );
}

// ---------- Session transcript (snapshot link + preview) ----------

interface TaskTranscriptPayload {
  task_id: string;
  session_id: string | null;
  agent: string | null;
  exists: boolean;
  relpath: string | null;
  size: number;
  line_count: number;
  recent: { role: string; preview: string; ts: string | null }[];
}

function TaskTranscriptPanel({ taskId }: { taskId: string }) {
  const { data } = useApiGet<TaskTranscriptPayload>(
    ['board-task-transcript', taskId],
    `/api/board/task/${taskId}/transcript`,
    { limit: 20 },
    { enabled: !!taskId },
  );
  const mono = "'JetBrains Mono', monospace";
  if (!data || !data.session_id) return null;
  return (
    <div style={{ marginTop: 20, borderTop: '1px solid var(--col-border)', paddingTop: 14 }}>
      <div
        style={{
          fontFamily: mono,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '.08em',
          color: 'var(--ink-soft)',
          marginBottom: 8,
        }}
      >
        SESSION
      </div>
      <div style={{ fontFamily: mono, fontSize: 11, color: 'var(--ink-faint)', marginBottom: 8 }}>
        {data.agent ? `${data.agent} · ` : ''}
        {data.session_id}
        {data.exists
          ? ` · transcript: ${data.line_count} lines (${data.relpath})`
          : ' · no snapshot on disk'}
      </div>
      {data.exists && data.recent.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            maxHeight: 240,
            overflow: 'auto',
            padding: '8px 10px',
            background: 'var(--board-grain)',
            border: '1px solid var(--col-border)',
            borderRadius: 4,
          }}
        >
          {data.recent.map((m, i) => (
            <div key={`${m.ts ?? ''}-${i}`} style={{ fontFamily: mono, fontSize: 11, lineHeight: 1.4 }}>
              <span
                style={{
                  color: m.role === 'assistant' ? 'var(--accent)' : 'var(--ink-soft)',
                  fontWeight: 700,
                }}
              >
                {m.role}
              </span>
              <span style={{ color: 'var(--ink)', marginLeft: 6 }}>
                {m.preview.length > 180 ? `${m.preview.slice(0, 180)}…` : m.preview}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
