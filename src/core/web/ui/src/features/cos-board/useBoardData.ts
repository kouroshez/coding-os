import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiGet } from '@/lib/api-client';
import { useBoardStream } from './useBoardStream';
import { KIND_COLORS, kindStyle } from './kindColors';
import { liveSessionsBySid } from './agentPresenceVisuals';
import { FALLBACK_AGENT_MANIFEST } from './board-shared';
import type { TaskCounts } from './board-shared';
import type {
  BoardConfigPayload,
  BoardListCard,
  BoardListPayload,
  BoardTweaks,
  ColumnDTO,
  SwimlaneDTO,
} from './types';

export interface SelectOption {
  value: string;
  label: string;
}

interface ColumnPage {
  cards: BoardListCard[];
  cursor: string | null;
}

/**
 * Board data layer: the two queries, the live stream, keyset pagination, and
 * every derived projection the grid renders from. Filtering depends on the
 * user's tweaks, so they come in as the single argument.
 */
export function useBoardData(tweaks: BoardTweaks) {
  const qc = useQueryClient();

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
  // accumulated here, then merged into `cards` below.
  const [extra, setExtra] = useState<Record<string, ColumnPage>>({});
  const [loadingMore, setLoadingMore] = useState<string | null>(null);

  const loadMore = useCallback(
    async (status: string) => {
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
    },
    [extra, list?.columns, loadingMore],
  );

  useEffect(() => {
    if (bump > 0) {
      // Keep accumulated load-more pages across SSE bumps — the card merge
      // dedups by id with the fresh first page winning, so a refetch can't
      // duplicate rows and the user's expansion survives.
      // queryKey prefix is ['cos-scope', slug, path, ...] — a plain-path
      // queryKey no longer matches, so `invalidateApiQueries` uses a
      // predicate to catch both scoped and unscoped entries.
      void invalidateApiQueries(qc, '/api/board/list');
      void invalidateApiQueries(qc, '/api/board/retro');
    }
  }, [bump, qc]);

  const cards: BoardListCard[] = useMemo(() => {
    const base = list?.cards ?? [];
    const extras = Object.values(extra).flatMap((e) => e.cards);
    if (extras.length === 0) return base;
    const seen = new Set(base.map((c) => c.id));
    return [...base, ...extras.filter((c) => !seen.has(c.id))];
  }, [list, extra]);

  const swimlanes: SwimlaneDTO[] = cfg?.swimlanes ?? [];
  // Filter archive out of the visible column list unless the user opts in via
  // the header toggle — archive is a soft-terminal cold store and most
  // sessions don't need to see it. Backend still returns archive cards in
  // `cards`, so the only concession when hidden is that those cards can't be
  // reached from the main grid (drawer deep-link still works).
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

  const kindOptions = useMemo<SelectOption[]>(
    () => [
      { value: 'all', label: 'all' },
      ...Object.keys(KIND_COLORS).map((k) => ({ value: k, label: kindStyle(k).label })),
    ],
    [],
  );
  const epicOptions = useMemo<SelectOption[]>(
    () => [
      { value: 'all', label: 'all' },
      ...Array.from(new Set(cards.map((t) => t.epic).filter((e): e is string => !!e))).map((e) => ({
        value: e,
        label: e,
      })),
    ],
    [cards],
  );

  return {
    list,
    cfg,
    isLoading,
    error,
    agentCatalog,
    liveSessions,
    connected,
    streamEvents,
    pushHumanEvent,
    cards,
    swimlanes,
    columns,
    filtered,
    cellMap,
    taskCounts,
    kindOptions,
    epicOptions,
    extra,
    loadingMore,
    loadMore,
  };
}

export type BoardData = ReturnType<typeof useBoardData>;
