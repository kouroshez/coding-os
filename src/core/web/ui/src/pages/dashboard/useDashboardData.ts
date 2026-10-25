import { useMemo } from 'react';
import { useApiGet } from '@/lib/hooks';
import type { MemoryPayload } from '../memory/memory-view';
import type { ActiveSessionsPayload, BoardListPayload, ChatsPayload } from './dashboard-types';

interface CountPayload {
  count?: number;
  installed?: unknown[];
}

const CONFIG_STALE_MS = 60_000;

// Every Overview fetch and the view model derived from it. Panels stay
// render-only, so a producer change lands in exactly one place.
export function useDashboardData() {
  const sessions = useApiGet<ActiveSessionsPayload>(
    ['sessions-active-dash'],
    '/api/sessions/active',
    undefined,
    { refetchIntervalMs: 4000 },
  );
  const board = useApiGet<BoardListPayload>(['board-dash'], '/api/board/list', undefined, {
    refetchIntervalMs: 8000,
  });
  const memory = useApiGet<MemoryPayload>(['memory'], '/api/memory');
  const chats = useApiGet<ChatsPayload>(['chats-dash'], '/api/cognition/chats', { limit: 5 });
  const configOptions = { staleTimeMs: CONFIG_STALE_MS };
  const stacks = useApiGet<CountPayload>(['cfg-stacks'], '/api/config/stacks', undefined, configOptions);
  const skills = useApiGet<CountPayload>(['cfg-skills'], '/api/config/skills', undefined, configOptions);
  const mcp = useApiGet<CountPayload>(['cfg-mcp'], '/api/config/mcp', undefined, configOptions);
  const adapters = useApiGet<CountPayload>(
    ['cfg-adapters'],
    '/api/config/adapters',
    undefined,
    configOptions,
  );

  const sessionRows = useMemo(
    () => (sessions.data?.sessions ?? []).filter((s) => s.state !== 'ended'),
    [sessions.data],
  );
  const liveCount = sessionRows.filter((s) => s.state === 'active' || s.state === 'present').length;

  const cards = useMemo(() => board.data?.cards ?? [], [board.data]);
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const card of cards) {
      const status = card.status ?? 'unknown';
      counts[status] = (counts[status] ?? 0) + 1;
    }
    return counts;
  }, [cards]);
  const activeCards = useMemo(
    () => cards.filter((c) => c.status === 'in_progress' || c.status === 'testing'),
    [cards],
  );

  const installed = {
    stacks: stacks.data?.installed?.length ?? null,
    skills: skills.data?.count ?? null,
    mcp: mcp.data?.count ?? null,
    adapters: adapters.data?.count ?? null,
  };

  const panelErrors: Array<[string, Error | null]> = [
    ['sessions', sessions.error],
    ['board', board.error],
    ['memory', memory.error],
    ['chats', chats.error],
  ];
  const failedPanels = panelErrors.filter((entry): entry is [string, Error] => entry[1] !== null);

  return {
    activeCards,
    board,
    cards,
    chats,
    failedPanels,
    installed,
    liveCount,
    memory,
    sessionRows,
    sessions,
    statusCounts,
    wipCap: board.data?.wip?.caps?.in_progress ?? 0,
  };
}
