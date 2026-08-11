import { useCallback, useMemo } from 'react';
import { useApiGet } from '@/lib/hooks';
import { useScopedLink } from '@/lib/use-scoped-link';
import type {
  ActiveSessionsPayload,
  BoardListPayload,
  ChatsPayload,
  ContextAgentsPayload,
  CostPayload,
  HooksRecentPayload,
  PresencePayload,
  SettingsPayload,
  TracesPayload,
} from './dashboard-types';

// Every dashboard fetch and the view model derived from it. Panels stay
// render-only, so a producer change lands in exactly one place.
export function useDashboardData() {
  const { scopedLink } = useScopedLink();
  const presence = useApiGet<PresencePayload>(
    ['presence-now'],
    '/api/presence/now',
    undefined,
    { refetchIntervalMs: 4000 },
  );
  const contextAgents = useApiGet<ContextAgentsPayload>(
    ['presence-agents-dash'],
    '/api/presence/agents',
    undefined,
    { refetchIntervalMs: 4000 },
  );
  const sessionsActive = useApiGet<ActiveSessionsPayload>(
    ['sessions-active-dash'],
    '/api/sessions/active',
    undefined,
    { refetchIntervalMs: 4000 },
  );
  const hooks = useApiGet<HooksRecentPayload>(
    ['hooks-recent-dash'],
    '/api/hooks/recent',
    { limit: 14 },
    { refetchIntervalMs: 4000 },
  );
  const chats = useApiGet<ChatsPayload>(['chats-dash'], '/api/cognition/chats', { limit: 6 });
  const traces = useApiGet<TracesPayload>(
    ['traces-dash'],
    '/api/cognition/traces',
    undefined,
    { refetchIntervalMs: 6000 },
  );
  const cost = useApiGet<CostPayload>(['cost-dash'], '/api/cognition/cost', { limit: 30 });
  const board = useApiGet<BoardListPayload>(['board-dash'], '/api/board/list', undefined, {
    refetchIntervalMs: 8000,
  });
  const settings = useApiGet<SettingsPayload>(['settings-dash'], '/api/settings');

  const todayKey = new Date().toISOString().slice(0, 10);
  const todayCost = useMemo(
    () =>
      (cost.data?.rows ?? [])
        .filter((r) => r.day === todayKey)
        .reduce((a, r) => a + r.total_cost_usd, 0),
    [cost.data, todayKey],
  );

  // 7-day rolling sparkline data — sum cost per day.
  const sparkline = useMemo(() => {
    const days: { day: string; total: number }[] = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
      const total = (cost.data?.rows ?? [])
        .filter((r) => r.day === d)
        .reduce((a, r) => a + r.total_cost_usd, 0);
      days.push({ day: d, total });
    }
    return days;
  }, [cost.data]);

  const wipCap = board.data?.wip?.caps?.in_progress ?? 0;
  const cards = board.data?.cards ?? [];
  const blocked = cards.filter((c) => c.status === 'blocked').length;
  const inProgress = cards.filter((c) => c.status === 'in_progress').length;
  const testing = cards.filter((c) => c.status === 'testing').length;
  const wipOver = wipCap > 0 && inProgress > wipCap;

  const budget = settings.data?.settings?.budget_cap;
  const budgetPct =
    budget?.enabled && budget.cap_usd > 0 ? Math.min(100, (todayCost / budget.cap_usd) * 100) : 0;

  // Live agents are derived from sessions/active, NOT from agent_states —
  // agent_states is keyed by canonical adapter id (claude, codex)
  // so two concurrent Claude sessions would collapse to one entry there.
  // sessions/active yields one record per `sessions/<sid>.json` file, so
  // every concurrent runtime gets its own row.
  const liveSessions = useMemo(() => {
    // `active` (tool/prompt within 30 s) and `present` (within 300 s
    // TTL) always count. `idle` (PID alive, no recent activity) is
    // excluded by default — on this repo it commonly means a long-dead
    // Claude Code process whose PID the OS recycled (inflated the KPI
    // to 21 when one agent worked — 2026-05-20 UI audit).
    // EXCEPTION: an `is_current` row IS the agent's live session (its
    // session_id matches the `session-id` marker), so a recycled PID
    // can't masquerade as it. A read-only session (verify/git/pytest,
    // no Write/Edit) that aged past the TTL classifies `idle` but is
    // still genuinely working — count it when its PID is alive.
    const all = sessionsActive.data?.sessions ?? [];
    return all
      .filter(
        (s) =>
          s.state === 'active' ||
          s.state === 'present' ||
          (s.is_current === true && s.state !== 'offline' && s.state !== 'ended'),
      )
      .filter((s) => s.agent !== 'human');
  }, [sessionsActive.data]);
  const presentCount = liveSessions.length;
  // Agent-shared snapshot (task / skill / gate live in $COS_AGENT_DIR
  // shared across the canonical agent's concurrent sessions) — only
  // attached to the row whose session_id matches the agent's current
  // active session marker.
  const agentSnapshot = useCallback(
    (agent: string) => presence.data?.agents.find((a) => a.agent === agent) ?? null,
    [presence.data],
  );

  const recentTraces = (traces.data?.sessions ?? []).slice(0, 5);
  const recentChats = (chats.data?.sessions ?? []).slice(0, 5);
  const recentHooks = (hooks.data?.events ?? []).slice(0, 12);

  // Every panel degrades to `?? []`, so a failed fetch would otherwise read as a
  // real zero. Name the panels that failed instead of showing confident zeros.
  const panelErrors: [string, Error | null][] = [
    ['presence', presence.error],
    ['sessions', sessionsActive.error],
    ['hooks', hooks.error],
    ['chats', chats.error],
    ['traces', traces.error],
    ['cost', cost.error],
    ['board', board.error],
    ['settings', settings.error],
  ];
  const failedPanels = panelErrors.filter((e): e is [string, Error] => e[1] != null);

  return {
    agentSnapshot,
    blocked,
    budget,
    budgetPct,
    cards,
    chats,
    contextAgents,
    cost,
    failedPanels,
    hooks,
    inProgress,
    liveSessions,
    presence,
    presentCount,
    recentChats,
    recentHooks,
    recentTraces,
    scopedLink,
    sessionsActive,
    sparkline,
    testing,
    todayCost,
    traces,
    wipCap,
    wipOver,
  };
}
