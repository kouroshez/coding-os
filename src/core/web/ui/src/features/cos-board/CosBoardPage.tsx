import {
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type DragEvent,
  type ReactNode,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiGet, apiPost } from '@/lib/api-client';
import { useBoardTheme } from './BoardThemeProvider';
import { useBoardStream, agentForSession } from './useBoardStream';
import { KIND_COLORS, kindStyle } from './kindColors';
import type {
  BoardConfigPayload,
  BoardListCard,
  BoardListPayload,
  ColumnDTO,
  SwimlaneDTO,
} from './types';
import { liveSessionsBySid } from './agentPresenceVisuals';
import {
  AgentCatalogContext,
  COLUMN_META,
  FALLBACK_AGENT_MANIFEST,
  LiveSessionsContext,
  alpha,
  columnWipCap,
  isPresenceAgent,
  lanePalette,
  priorityStyle,
  useAgentCatalog,
} from './board-shared';
import type {
  AgentState,
  CreateTaskResponse,
  Highlight,
  TaskCounts,
} from './board-shared';
import { TaskDetailDrawer } from './task-detail';
import { AgentTaskModal, CreateTaskModal } from './board-modals';
import { AgentBadge, LiveAgentPip } from './AgentBadges';
import { LiveStreamPanel, TweaksPanel, LegendPanel, ZoomControls } from './board-panels';

// ============================================================
// Main page
// ============================================================
export default function CosBoardPage() {
  const qc = useQueryClient();
  const { tweaks, setTweaks } = useBoardTheme();

  const { data: list, isLoading, error } = useApiGet<BoardListPayload>(
    ['board-list'],
    '/api/board/list',
    { limit: 400, include_archive: true },
  );
  const { data: cfg } = useApiGet<BoardConfigPayload>(['board-config'], '/api/board/config');

  // Single source of truth for "which agents exist": the live manifest from
  // /api/board/list, falling back to the static list only on an older Hub.
  // Both the stream (agentForSession) and the live-agents strip read it.
  const agentCatalog = useMemo(
    () =>
      list?.agent_manifest && list.agent_manifest.length > 0
        ? list.agent_manifest
        : FALLBACK_AGENT_MANIFEST,
    [list?.agent_manifest],
  );
  const agentIds = useMemo(() => agentCatalog.map((a) => a.id), [agentCatalog]);

  const liveSessions = useMemo(
    () => liveSessionsBySid(list?.session_states),
    [list?.session_states],
  );

  const { bump, connected, events: streamEvents, pushHumanEvent } = useBoardStream(agentIds);

  // Per-column "load more" for the keyset-paged columns (complete/archive).
  // The first page arrives in `list`; each extra page is fetched on demand and
  // accumulated here, then merged into `cards` below. Reset on SSE bump so a
  // refreshed first page never duplicates accumulated rows. TASK-223.
  const [extra, setExtra] = useState<Record<string, { cards: BoardListCard[]; cursor: string | null }>>({});
  const [loadingMore, setLoadingMore] = useState<string | null>(null);

  async function loadMore(status: string) {
    const cur = extra[status]?.cursor ?? list?.columns?.[status]?.next_cursor ?? null;
    if (!cur || loadingMore) return;
    setLoadingMore(status);
    try {
      const [page] = await apiGet<BoardListPayload>('/api/board/list', {
        status,
        cursor: cur,
        page_size: 50,
        include_archive: true,
      });
      setExtra((prev) => ({
        ...prev,
        [status]: {
          cards: [...(prev[status]?.cards ?? []), ...(page.cards ?? [])],
          cursor: page.columns?.[status]?.next_cursor ?? null,
        },
      }));
    } finally {
      setLoadingMore(null);
    }
  }

  useEffect(() => {
    if (bump > 0) {
      // Keep accumulated load-more pages across SSE bumps (TASK-399) — the
      // card merge dedups by id with the fresh first page winning, so a
      // refetch can't duplicate rows and the user's expansion survives.
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
  const [agentOpen, setAgentOpen] = useState<boolean>(false);
  const [detailTask, setDetailTask] = useState<BoardListCard | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

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

  const cards: BoardListCard[] = useMemo(() => {
    const base = list?.cards ?? [];
    const extras = Object.values(extra).flatMap((e) => e.cards);
    if (extras.length === 0) return base;
    const seen = new Set(base.map((c) => c.id));
    return [...base, ...extras.filter((c) => !seen.has(c.id))];
  }, [list, extra]);
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

  // Deep-link focus: /workspace/board?task=TASK-NNN (e.g. from search) opens
  // that task's drawer, then consumes the param so a later close doesn't
  // re-open it. No-op until the card is present in the loaded board list.
  useEffect(() => {
    const focus = searchParams.get('task');
    if (!focus) return;
    const card = cards.find((c) => c.id === focus);
    if (!card) return;
    setDetailTask(card);
    const next = new URLSearchParams(searchParams);
    next.delete('task');
    setSearchParams(next, { replace: true });
  }, [searchParams, cards, setSearchParams]);

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
    <LiveSessionsContext.Provider value={liveSessions}>
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <TopBar
        taskCount={list?.count ?? 0}
        connected={connected}
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
        showSwimlanes={tweaks.showSwimlanes}
        onToggleLegend={() => setLegendOpen((v) => !v)}
        onToggleStream={() => setStreamOpen((v) => !v)}
        onToggleArchive={() => setTweaks((t) => ({ ...t, showArchive: !t.showArchive }))}
        onToggleSwimlanes={() => setTweaks((t) => ({ ...t, showSwimlanes: !t.showSwimlanes }))}
        onToggleTweaks={() => setTweaksOpen((v) => !v)}
        onCreate={() => setCreateOpen(true)}
        onOpenTask={setDetailTask}
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
              const meta = COLUMN_META[col.id] ?? { label: col.label, sub: '', wip: null, tint: 'var(--ink-faint)' };
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
                      borderTop: `3px solid ${meta.tint}`,
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
                      title={
                        cap != null
                          ? `WIP = work-in-progress limit: at most ${cap} task${cap !== 1 ? 's' : ''} may sit in “${meta.label}” at once`
                          : undefined
                      }
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 10,
                        color: violated ? 'var(--red-ink)' : 'var(--ink-faint)',
                        marginTop: 2,
                        fontWeight: violated ? 700 : 500,
                        cursor: cap != null ? 'help' : 'default',
                      }}
                    >
                      {count}
                      {cap != null ? ` / ${cap} WIP` : ' tasks'}
                      {violated && ' ⚠'}
                      {flashWip === col.id && <span style={{ marginLeft: 6 }}>WIP!</span>}
                    </div>
                    {(() => {
                      // Keyset-paged columns (complete/archive) show rendered /
                      // total + a "load more" affordance. TASK-223.
                      const colMeta = list?.columns?.[col.id];
                      if (!colMeta || colMeta.total_count == null) return null;
                      const rendered = filtered.filter((t) => t.status === col.id).length;
                      const more = extra[col.id]?.cursor ?? colMeta.next_cursor;
                      return (
                        <div
                          style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            fontSize: 10,
                            color: 'var(--ink-faint)',
                            marginTop: 1,
                          }}
                        >
                          {rendered} / {colMeta.total_count}
                          {more && (
                            <button
                              type="button"
                              onClick={() => void loadMore(col.id)}
                              disabled={loadingMore === col.id}
                              style={{
                                marginLeft: 6,
                                cursor: loadingMore === col.id ? 'wait' : 'pointer',
                                font: 'inherit',
                                border: '1px solid var(--col-border)',
                                borderRadius: 4,
                                background: 'transparent',
                                color: 'var(--ink-soft)',
                                padding: '0 5px',
                              }}
                            >
                              {loadingMore === col.id ? '…' : '+ more'}
                            </button>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                </div>
              );
            })}
          </div>

          {tweaks.showSwimlanes && swimlanes.map((lane, laneIdx) => {
            const laneCount = filtered.filter((t) => t.swimlane === lane.id).length;
            const isCollapsed = collapsed.has(lane.id);
            const palette = lanePalette(lane);
            if (isCollapsed) {
              const expandLane = () =>
                setCollapsed((prev) => {
                  const n = new Set(prev);
                  n.delete(lane.id);
                  return n;
                });
              return (
                <div
                  key={lane.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`Expand ${lane.label} lane`}
                  onClick={expandLane}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      expandLane();
                    }
                  }}
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

          {!tweaks.showSwimlanes && (
            <div style={{ display: 'flex', borderBottom: '1px solid var(--col-border)', minHeight: 200 }}>
              <div
                style={{
                  width: 130,
                  minWidth: 130,
                  flexShrink: 0,
                  borderRight: '2px solid var(--line)',
                  position: 'sticky',
                  left: 0,
                  zIndex: 1,
                  background: 'var(--board)',
                }}
              />
              {columns.map((col) => {
                const cell = filtered.filter((t) => t.status === col.id);
                const laneId = dragging?.swimlane ?? '__flat__';
                const isTarget = dragTarget === `${laneId}:${col.id}`;
                const cap = columnWipCap(col.id, cfg?.wip_limits);
                const violated = cap != null && cell.length > cap;
                return (
                  <div
                    key={col.id}
                    onDragOver={(e) => onDragOver(e, dragging?.swimlane ?? '__flat__', col.id)}
                    onDrop={(e) => void onDrop(e, dragging?.swimlane ?? col.id, col.id)}
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
                    {cell.map((task) => {
                      const sl = swimlanes.find((s) => s.id === task.swimlane);
                      const lp = sl
                        ? lanePalette(sl)
                        : { color: 'var(--ink-soft)', accent: 'var(--ink-soft)' };
                      return (
                        <TaskStickyCard
                          key={task.id}
                          task={task}
                          laneColor={lp.color}
                          laneAccent={lp.accent}
                          density={tweaks.density}
                          quietMode={tweaks.quietMode}
                          agentSurface={tweaks.agentSurface}
                          highlight={highlight}
                          draggingId={dragging?.id || ''}
                          onDragStart={onDragStart}
                          onDragEnd={onDragEnd}
                          onOpen={setDetailTask}
                        />
                      );
                    })}
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
          )}

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

      <AgentTaskModal
        open={agentOpen}
        onClose={() => setAgentOpen(false)}
        onDone={() => {
          void invalidateApiQueries(qc, '/api/board/list');
        }}
      />

      <CreateTaskModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onAgentMode={() => {
          setCreateOpen(false);
          setAgentOpen(true);
        }}
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
    </LiveSessionsContext.Provider>
    </AgentCatalogContext.Provider>
  );
}

// ============================================================
// TopBar
// ============================================================
function TopBar({
  taskCount,
  connected,
  agentStates,
  sessionCounts,
  legendOpen,
  streamOpen,
  showArchive,
  showSwimlanes,
  onToggleLegend,
  onToggleStream,
  onToggleArchive,
  onToggleSwimlanes,
  onToggleTweaks,
  onCreate,
  onOpenTask,
}: {
  taskCount: number;
  connected: boolean;
  agentStates: Record<string, AgentState>;
  sessionCounts?: Record<string, number>;
  legendOpen: boolean;
  streamOpen: boolean;
  showArchive: boolean;
  showSwimlanes: boolean;
  onToggleLegend: () => void;
  onToggleStream: () => void;
  onToggleArchive: () => void;
  onToggleSwimlanes: () => void;
  onToggleTweaks: () => void;
  onCreate: () => void;
  onOpenTask: (card: BoardListCard) => void;
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
            {agentRows.filter(isPresenceAgent).map((a) => (
              <AgentBadge
                key={a.id}
                agentId={a.id}
                state={agentStates[a.id] ?? 'offline'}
                sessionCount={sessionCounts?.[a.id]}
              />
            ))}
          </div>
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

        <SuggestNextButton onOpenTask={onOpenTask} />
        <TopBtn onClick={onToggleLegend} active={legendOpen}>⁂ legend</TopBtn>
        <TopBtn onClick={onToggleStream} active={streamOpen}>⎌ stream</TopBtn>
        <TopBtn onClick={onToggleSwimlanes} active={showSwimlanes}>
          {showSwimlanes ? '☰ swimlanes' : '▦ flat'}
        </TopBtn>
        <TopBtn onClick={onToggleArchive} active={showArchive}>
          {showArchive ? '▣ archive on' : '▢ archive'}
        </TopBtn>
        <TopBtn onClick={onToggleTweaks}>⚙ tweaks</TopBtn>
      </div>
    </div>
  );
}

export function SuggestNextButton({ onOpenTask }: { onOpenTask: (card: BoardListCard) => void }) {
  // Producer: GET /api/board/pick → {candidates: BoardListCard[], count}
  // (board.py::board_pick wrapping cos_task_pick — emergency first, then
  // ready icebox by priority). Zero UI consumers before TASK-322.
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<BoardListCard[] | null>(null);

  const fetchPick = async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    try {
      const [data] = await apiGet<{ candidates: BoardListCard[]; count: number }>(
        '/api/board/pick?max_candidates=5',
      );
      setCandidates(data.candidates);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'pick failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position: 'relative' }}>
      <TopBtn onClick={() => (open ? setOpen(false) : void fetchPick())} active={open}>
        ◎ suggest next
      </TopBtn>
      {open && (
        <div
          role="listbox"
          aria-label="Suggested next tasks"
          style={{
            position: 'absolute',
            top: '110%',
            right: 0,
            zIndex: 60,
            width: 340,
            maxHeight: 320,
            overflow: 'auto',
            background: 'var(--board)',
            border: '1px solid var(--col-border)',
            borderRadius: 6,
            boxShadow: '0 8px 24px rgba(0,0,0,.35)',
            padding: 6,
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
          }}
        >
          {loading && <div style={{ padding: 8, color: 'var(--ink-faint)' }}>picking…</div>}
          {error && <div style={{ padding: 8, color: 'var(--cos-err)' }}>{error}</div>}
          {!loading && !error && candidates !== null && candidates.length === 0 && (
            <div style={{ padding: 8, color: 'var(--ink-faint)' }}>
              no pullable task — nothing in emergency or ready icebox
            </div>
          )}
          {!loading &&
            !error &&
            (candidates ?? []).map((card) => (
              <button
                key={card.id}
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => {
                  setOpen(false);
                  onOpenTask(card);
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '7px 8px',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: 4,
                  cursor: 'pointer',
                  color: 'var(--ink)',
                }}
              >
                <span style={{ fontWeight: 700 }}>{card.id}</span>{' '}
                <span style={{ color: 'var(--ink-faint)' }}>
                  {card.priority}
                  {card.status === 'emergency' ? ' · emergency' : ' · ready'}
                </span>
                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {card.title}
                </div>
              </button>
            ))}
        </div>
      )}
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
  const agentCatalog = useAgentCatalog();

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

  const agentId = task.agent_session
    ? agentForSession(task.agent_session, agentCatalog.map((a) => a.id))
    : null;

  return (
    <div
      draggable
      role="button"
      tabIndex={0}
      aria-label={`Open task ${task.id}: ${task.title}`}
      onDragStart={(e) => onDragStart(e, task)}
      onDragEnd={onDragEnd}
      onClick={() => onOpen(task)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(task);
        }
      }}
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
          {agentId && agentSurface && (
            <LiveAgentPip agentId={agentId} session={task.agent_session} />
          )}
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

