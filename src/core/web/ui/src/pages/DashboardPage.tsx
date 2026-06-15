import { useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertOctagon,
  Brain,
  CircleDollarSign,
  KanbanSquare,
  MessageSquare,
  Sparkles,
  Users,
  Zap,
} from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { useScopedLink } from '@/lib/use-scoped-link';

// ─────────────────────────────────────────────────────────────────────────
// Types — minimal slice of each upstream payload that the dashboard reads.
// ─────────────────────────────────────────────────────────────────────────

interface PresenceAgent {
  agent: string;
  session_id?: string | null;
  task?: string | null;
  skill_active?: string | null;
  model?: string | null;
  gate?: string | null;
  session?: {
    started_at?: number | null;
    last_tool_at?: number | null;
    last_prompt_at?: number | null;
    pid?: number | null;
  } | null;
}
interface PresencePayload {
  agents: PresenceAgent[];
  agent_states: Record<string, string>;
  last_hook: HookEvent | null;
  current_chat_uuid: string | null;
}

// Producer: /api/presence/agents (presence.py::presence_agents) — the
// context-window fill the hub-architecture spec documents (TASK-324).
interface ContextAgent {
  agent: string;
  session_id?: string | null;
  context_pct: number | null;
  used_tokens?: number | null;
  context_window?: number | null;
}
interface ContextAgentsPayload {
  agents: ContextAgent[];
}

interface ActiveSession {
  agent: string;
  session_id: string;
  pid: number | null;
  started_at: number | null;
  last_prompt_at: number | null;
  last_tool_at: number | null;
  last_stop_at: number | null;
  ended_at: number | null;
  state: 'active' | 'present' | 'idle' | 'offline' | 'ended';
  is_current?: boolean;
  model?: string | null;
}
interface ActiveSessionsPayload {
  sessions: ActiveSession[];
  counts: Record<string, number>;
  now: number;
  ttl_s: number;
}

interface HookEvent {
  iso_ts: string;
  hook: string;
  action: string;
  agent: string;
  session_id: string;
  task: string;
}
interface HooksRecentPayload {
  events: HookEvent[];
  count: number;
}

interface ChatSession {
  session_id: string;
  summary?: string | null;
  custom_title?: string | null;
  first_prompt?: string | null;
  last_modified?: number | null;
  git_branch?: string | null;
  file_size?: number | null;
}
interface ChatsPayload {
  sessions: ChatSession[];
}

interface TraceSession {
  agent: string;
  session_id: string;
  event_count?: number;
  first_event_kind?: string | null;
  mtime_ts?: number;
  source?: string;
  is_active?: boolean;
}
interface TracesPayload {
  sessions: TraceSession[];
  count: number;
  trace_count: number;
  session_count: number;
}

interface CostRow {
  formula_id: string;
  day: string;
  total_cost_usd: number;
  count: number;
}
interface CostPayload {
  rows: CostRow[];
  total_usd: number;
  count: number;
}

interface BoardListPayload {
  cards: { task_id: string; title?: string; status?: string; swimlane?: string }[];
  wip?: { counts: Record<string, number>; caps: Record<string, number> };
}

interface SettingsPayload {
  settings: {
    budget_cap?: { enabled: boolean; cap_usd: number };
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Visual tokens
// ─────────────────────────────────────────────────────────────────────────

const STATE_DOT: Record<string, { color: string; pulse: boolean; label: string }> = {
  active: { color: '#16a34a', pulse: true, label: 'active' },
  working: { color: '#16a34a', pulse: true, label: 'working' },
  present: { color: '#fbbf24', pulse: false, label: 'present' },
  idle: { color: '#fbbf24', pulse: false, label: 'idle' },
  offline: { color: '#6b7280', pulse: false, label: 'offline' },
};

// Every badge: a faint themed tint bg + the solid hue as text (AA-verified
// in both themes via scripts/badge_contrast.py). Neutral statuses get a
// visible border-tint, never bg=panel. `label` overrides the rendered text
// so long action names aren't clipped.
const NEUTRAL_BADGE = { bg: 'bg-[var(--cos-border)]/40', text: 'text-[var(--cos-muted)]' };
const ACTION_BADGE: Record<string, { bg: string; text: string; label?: string }> = {
  fire: { bg: 'bg-[var(--cos-info-tint)]', text: 'text-[var(--cos-info)]' },
  block: { bg: 'bg-[var(--cos-err-tint)]', text: 'text-[var(--cos-err)]' },
  warn: { bg: 'bg-[var(--cos-warn-tint)]', text: 'text-[var(--cos-warn)]' },
  'stale-gate': { bg: 'bg-[var(--cos-warn-tint)]', text: 'text-[var(--cos-warn)]', label: 'stale' },
  skip: { ...NEUTRAL_BADGE },
  'skip-not-replace': { ...NEUTRAL_BADGE, label: 'skip' },
  pass: { bg: 'bg-[var(--cos-ok-tint)]', text: 'text-[var(--cos-ok)]' },
  ok: { bg: 'bg-[var(--cos-ok-tint)]', text: 'text-[var(--cos-ok)]' },
  entry: { bg: 'bg-[var(--cos-brand-tint)]', text: 'text-[var(--cos-brand-text)]' },
  enter: { bg: 'bg-[var(--cos-brand-tint)]', text: 'text-[var(--cos-brand-text)]' },
  dispatched: { bg: 'bg-[var(--cos-live-tint)]', text: 'text-[var(--cos-live)]', label: 'disp' },
  'session-end': { ...NEUTRAL_BADGE, label: 'end' },
  posttooluse: { bg: 'bg-[var(--cos-brand-tint)]', text: 'text-[var(--cos-brand-text)]', label: 'post' },
  pretooluse: { bg: 'bg-[var(--cos-brand-tint)]', text: 'text-[var(--cos-brand-text)]', label: 'pre' },
  'non-rename': { ...NEUTRAL_BADGE, label: 'keep' },
};

// ─────────────────────────────────────────────────────────────────────────
// Format helpers
// ─────────────────────────────────────────────────────────────────────────

function rel(ms: number | null | undefined): string {
  if (!ms) return '';
  const diff = (Date.now() - ms) / 1000;
  if (diff < 1) return 'now';
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function relIso(iso: string | null | undefined): string {
  if (!iso) return '';
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? rel(ms) : '';
}

function ageBadge(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return '';
  return rel(epochSeconds * 1000);
}

function compactSession(sid?: string | null): string {
  if (!sid) return '';
  if (sid.startsWith('ses-')) return sid.split('-').slice(-2).join('-');
  return sid.slice(0, 8);
}

// ─────────────────────────────────────────────────────────────────────────
// Dashboard root
// ─────────────────────────────────────────────────────────────────────────

export function ContextPctBadge({ row }: { row?: ContextAgent }) {
  // Explicit unknown state — never 0%, never blank (TASK-324 acceptance).
  if (!row || row.context_pct === null || row.context_pct === undefined) {
    return (
      <span
        className="font-mono text-[10px] text-[var(--cos-faint)]"
        title="context fill unknown — no usage signal for this session yet"
      >
        ctx ?
      </span>
    );
  }
  const pct = Math.round(row.context_pct);
  const tone =
    pct >= 85 ? 'var(--cos-err)' : pct >= 60 ? 'var(--cos-warn)' : 'var(--cos-ok)';
  const detail =
    row.used_tokens && row.context_window
      ? `${row.used_tokens.toLocaleString()} / ${row.context_window.toLocaleString()} tokens`
      : 'context window fill';
  return (
    <span className="font-mono text-[10px]" style={{ color: tone }} title={detail}>
      ctx {pct}%
    </span>
  );
}

export default function DashboardPage() {
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

  return (
    <div className="flex h-full flex-col overflow-auto bg-[var(--cos-bg)] p-6 cos-scroll">
      <DashboardHeader presentCount={presentCount} lastHook={presence.data?.last_hook ?? null} />

      {/* KPI strip — 4 narrow cards */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard
          Icon={Users}
          label="agents live"
          value={presentCount === 0 ? '—' : String(presentCount)}
          tone={presentCount > 0 ? 'positive' : 'neutral'}
          hint={(() => {
            if (presentCount === 0) return 'no agent running';
            const total = sessionsActive.data?.sessions.length ?? presentCount;
            const offline = Math.max(0, total - presentCount);
            return offline > 0 ? `${presentCount} live · ${offline} offline` : `${presentCount} session${presentCount === 1 ? '' : 's'}`;
          })()}
        />
        <KpiCard
          Icon={CircleDollarSign}
          label="today cost"
          value={`$${todayCost.toFixed(4)}`}
          tone={budget?.enabled && budgetPct > 80 ? 'warning' : 'neutral'}
          hint={
            budget?.enabled
              ? `${budgetPct.toFixed(0)}% of $${budget.cap_usd.toFixed(2)} cap`
              : 'no budget set'
          }
          bar={budget?.enabled ? { pct: budgetPct, warn: budgetPct > 80 } : undefined}
        />
        <KpiCard
          Icon={KanbanSquare}
          label="in progress"
          value={String(inProgress)}
          tone={wipOver ? 'warning' : 'neutral'}
          hint={wipCap > 0 ? `${inProgress}/${wipCap} cap` : `${cards.length} tasks total`}
        />
        <KpiCard
          Icon={AlertOctagon}
          label="blocked"
          value={String(blocked)}
          tone={blocked > 0 ? 'danger' : 'positive'}
          hint={blocked > 0 ? 'attention needed' : 'all clear'}
        />
      </div>

      {/* Quick actions — 1 row of CTAs */}
      <QuickActions
        currentChat={presence.data?.current_chat_uuid ?? null}
        activeSessionAgent={liveSessions[0]?.agent ?? null}
        activeSession={liveSessions[0]?.session_id ?? null}
        scopedLink={scopedLink}
      />

      {/* Main grid — 3 cols on xl, 2 on md */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <PanelCard
          Icon={Sparkles}
          title="Live agents"
          link={null}
        >
          {liveSessions.length === 0 ? (
            <EmptyState
              icon="●"
              text="No agent running right now"
              subtext="open a Claude / Codex session in this repo to see live runtime."
            />
          ) : (
            <ul className="space-y-2">
              {liveSessions.map((s) => {
                const snap = agentSnapshot(s.agent);
                // task/skill/gate live in $COS_AGENT_DIR shared across
                // concurrent sessions of the same canonical agent — only
                // attach to the row whose session matches the agent's
                // current session_id marker.
                const isActiveSession = snap?.session_id === s.session_id;
                const dot = STATE_DOT[s.state] ?? STATE_DOT.offline;
                return (
                  <li
                    key={s.session_id}
                    className="rounded-md border border-[var(--cos-border)] bg-[var(--cos-bg)] p-2.5"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        aria-hidden
                        className={[
                          'inline-block h-2.5 w-2.5 rounded-full',
                          dot.pulse ? 'animate-pulse' : '',
                        ].join(' ')}
                        style={{ background: dot.color }}
                      />
                      <span className="font-semibold text-[var(--cos-text)]">{s.agent}</span>
                      <Badge tone="muted">{dot.label}</Badge>
                      {s.model && (
                        <span className="ml-auto font-mono text-[10px] text-[var(--cos-faint)]">
                          {s.model}
                        </span>
                      )}
                      <ContextPctBadge
                        row={contextAgents.data?.agents.find(
                          (a) => a.session_id === s.session_id || a.agent === s.agent,
                        )}
                      />
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 font-mono text-[10px] text-[var(--cos-muted)]">
                      <span className="truncate">{s.session_id}</span>
                      {s.started_at && (
                        <span
                          className="rounded bg-[var(--cos-panel)] px-1.5 py-0.5 text-[var(--cos-faint)]"
                          title={`Started ${new Date(s.started_at * 1000).toLocaleString()}`}
                        >
                          age {ageBadge(s.started_at)}
                        </span>
                      )}
                      {s.pid && <span className="text-[var(--cos-faint)]">pid {s.pid}</span>}
                      {s.last_tool_at && (
                        <span className="text-[var(--cos-faint)]">
                          last tool {ageBadge(s.last_tool_at)}
                        </span>
                      )}
                    </div>
                    {isActiveSession && (
                      <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-[var(--cos-muted)]">
                        {snap?.task && (
                          <span className="col-span-2 truncate" title={snap.task}>
                            <span className="text-[var(--cos-faint)]">task </span>
                            <span className="text-[var(--cos-text)]">{snap.task}</span>
                          </span>
                        )}
                        {snap?.skill_active && (
                          <span className="col-span-2 truncate" title={snap.skill_active}>
                            <span className="text-[var(--cos-faint)]">skill </span>
                            <span>{snap.skill_active}</span>
                          </span>
                        )}
                        {snap?.gate && (
                          <span className="col-span-2 truncate">
                            <span className="text-[var(--cos-faint)]">gate </span>
                            <span className="font-mono">{snap.gate}</span>
                          </span>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </PanelCard>

        <PanelCard
          Icon={Zap}
          title="Recent hooks"
          link={scopedLink('cognition', '?view=live')}
          linkLabel="live →"
        >
          {hooks.isLoading && recentHooks.length === 0 ? (
            <Skeleton rows={6} />
          ) : recentHooks.length === 0 ? (
            <EmptyState icon="∅" text="No hook events" subtext="hooks fire when the agent uses tools." />
          ) : (
            <ul className="-mx-1 space-y-0.5">
              {recentHooks.map((e) => (
                <li
                  key={`${e.iso_ts}-${e.hook}-${e.session_id}`}
                  className="flex items-center gap-2 rounded px-1 py-1 hover:bg-[var(--cos-grain)]"
                >
                  <ActionBadge action={e.action} />
                  <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[var(--cos-text)]">
                    {e.hook}
                  </span>
                  <span className="shrink-0 font-mono text-[9px] text-[var(--cos-faint)]">{relIso(e.iso_ts)}</span>
                </li>
              ))}
            </ul>
          )}
        </PanelCard>

        <PanelCard
          Icon={CircleDollarSign}
          title="Cost · 7 days"
          link={scopedLink('cognition')}
          linkLabel="dispatchers →"
        >
          <div className="mb-2 flex items-baseline gap-2">
            <span className="font-mono text-2xl font-semibold text-[var(--cos-text)]">
              ${todayCost.toFixed(4)}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">today</span>
            <span className="ml-auto text-[10px] text-[var(--cos-faint)]">
              all-time ${(cost.data?.total_usd ?? 0).toFixed(4)}
            </span>
          </div>
          <Sparkbars data={sparkline} />
          {budget?.enabled && (
            <div className="mt-3">
              <div className="flex items-baseline justify-between text-[10px] text-[var(--cos-muted)]">
                <span>budget</span>
                <span>
                  ${todayCost.toFixed(4)} / ${budget.cap_usd.toFixed(2)}
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--cos-border)]/30">
                <div
                  className={[
                    'h-full transition-all',
                    budgetPct > 80
                      ? 'bg-[var(--cos-err-tint)]'
                      : budgetPct > 50
                      ? 'bg-[var(--cos-warn-tint)]'
                      : 'bg-[var(--cos-ok-tint)]',
                  ].join(' ')}
                  style={{ width: `${budgetPct}%` }}
                />
              </div>
            </div>
          )}
          {!budget?.enabled && (
            <p className="mt-2 text-[10px] text-[var(--cos-faint)]">
              no daily cap configured —{' '}
              <Link to="/settings" className="text-[var(--cos-accent)] hover:underline">
                set in Settings
              </Link>
            </p>
          )}
        </PanelCard>

        <PanelCard
          Icon={MessageSquare}
          title="Recent chats"
          link={scopedLink('cognition', '?view=chat')}
          linkLabel="all chats →"
        >
          {chats.isLoading && recentChats.length === 0 ? (
            <Skeleton rows={4} />
          ) : recentChats.length === 0 ? (
            <EmptyState icon="∅" text="No chat sessions yet" subtext="open Claude Code in this folder to start one." />
          ) : (
            <ul className="space-y-1.5">
              {recentChats.map((c) => (
                <li key={c.session_id}>
                  <Link
                    to={scopedLink('cognition', `${encodeURIComponent(c.session_id)}?view=chat`)}
                    className="block rounded-md border border-transparent px-2 py-1.5 transition-colors hover:border-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/5"
                  >
                    <div className="truncate text-xs font-semibold text-[var(--cos-text)]" dir="auto">
                      {c.custom_title ?? c.summary ?? c.first_prompt ?? c.session_id}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[9px] text-[var(--cos-muted)]">
                      <span className="font-mono">{c.session_id.slice(0, 8)}…</span>
                      {c.git_branch && (
                        <>
                          <span aria-hidden>·</span>
                          <span>{c.git_branch}</span>
                        </>
                      )}
                      {c.file_size != null && (
                        <>
                          <span aria-hidden>·</span>
                          <span>{(c.file_size / (1024 * 1024)).toFixed(1)}mb</span>
                        </>
                      )}
                      <span className="ml-auto">{rel(c.last_modified)}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </PanelCard>

        <PanelCard
          Icon={Brain}
          title="Recent traces"
          link={scopedLink('cognition')}
          linkLabel="all traces →"
        >
          {traces.isLoading && recentTraces.length === 0 ? (
            <Skeleton rows={4} />
          ) : recentTraces.length === 0 ? (
            <EmptyState icon="∅" text="No trace sessions" subtext="cognition events appear when the agent calls cos_* tools." />
          ) : (
            <ul className="space-y-1.5">
              {recentTraces.map((t) => (
                <li key={`${t.agent}-${t.session_id}`}>
                  <Link
                    to={scopedLink('cognition', encodeURIComponent(t.session_id))}
                    className="block rounded-md border border-transparent px-2 py-1.5 transition-colors hover:border-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/5"
                  >
                    <div className="flex items-center gap-2">
                      <AgentBadge agent={t.agent} active={t.is_active ?? false} />
                      <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-[var(--cos-text)]">
                        {compactSession(t.session_id)}
                      </span>
                      <span className="shrink-0 text-[9px] text-[var(--cos-faint)]">
                        {rel(t.mtime_ts ? t.mtime_ts * 1000 : null)}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[9px] text-[var(--cos-muted)]">
                      {t.first_event_kind && <span className="font-mono">{t.first_event_kind}</span>}
                      <span aria-hidden>·</span>
                      <span>{t.event_count ?? 0}ev</span>
                      <span aria-hidden>·</span>
                      <span>{t.source}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </PanelCard>

        <PanelCard
          Icon={Activity}
          title="Board summary"
          link={scopedLink('board')}
          linkLabel="open board →"
        >
          <div className="grid grid-cols-3 gap-2">
            <StatTile label="in progress" value={inProgress} tone={wipOver ? 'warning' : 'neutral'} subtitle={wipCap > 0 ? `/${wipCap}` : undefined} />
            <StatTile label="testing" value={testing} />
            <StatTile label="blocked" value={blocked} tone={blocked > 0 ? 'danger' : 'neutral'} />
          </div>
          {cards.length > 0 ? (
            <ul className="mt-3 space-y-1">
              {cards
                .filter((c) => c.status === 'in_progress' || c.status === 'blocked')
                .slice(0, 4)
                .map((c) => (
                  <li
                    key={c.task_id}
                    className="flex items-center gap-2 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 text-[11px]"
                  >
                    <Badge tone={c.status === 'blocked' ? 'danger' : 'accent'}>
                      {c.status?.replace('_', ' ')}
                    </Badge>
                    <span className="truncate font-mono text-[10px] text-[var(--cos-muted)]">
                      {c.task_id}
                    </span>
                    <span className="ml-auto min-w-0 flex-1 truncate text-[var(--cos-text)]">
                      {c.title}
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="mt-3 text-[10px] text-[var(--cos-faint)]">
              no tasks — create one in <Link to={scopedLink('board')} className="text-[var(--cos-accent)] hover:underline">Board</Link>.
            </p>
          )}
        </PanelCard>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Building blocks
// ─────────────────────────────────────────────────────────────────────────

function DashboardHeader({
  presentCount,
  lastHook,
}: {
  presentCount: number;
  lastHook: HookEvent | null;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h1 className="text-xl font-semibold text-[var(--cos-text)]">Overview</h1>
        <p className="mt-0.5 text-xs text-[var(--cos-muted)]">
          {presentCount > 0 ? (
            <>
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--cos-ok-tint)] align-middle" />{' '}
              {presentCount} agent{presentCount === 1 ? '' : 's'} live · last hook{' '}
              <span className="font-mono text-[var(--cos-text)]">
                {lastHook?.hook ?? '—'}
              </span>{' '}
              <span className="text-[var(--cos-faint)]">{relIso(lastHook?.iso_ts)} ago</span>
            </>
          ) : (
            'idle · open Claude / Codex to see live activity.'
          )}
        </p>
      </div>
    </header>
  );
}

function QuickActions({
  currentChat,
  activeSessionAgent,
  activeSession,
  scopedLink,
}: {
  currentChat: string | null;
  activeSessionAgent: string | null;
  activeSession: string | null;
  scopedLink: (featurePath: string, suffix?: string) => string;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {currentChat && (
        <Link
          to={scopedLink('cognition', `${encodeURIComponent(currentChat)}?view=chat`)}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 px-3 py-1.5 text-[11px] font-semibold text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/20"
        >
          <MessageSquare size={12} aria-hidden /> Open current chat
        </Link>
      )}
      {activeSession && (
        <Link
          to={scopedLink('cognition', encodeURIComponent(activeSession))}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
        >
          <Brain size={12} aria-hidden /> {activeSessionAgent ?? 'agent'} trace
        </Link>
      )}
      <Link
        to={scopedLink('cognition', '?view=live')}
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
      >
        <Zap size={12} aria-hidden /> Live hook stream
      </Link>
      <Link
        to={scopedLink('board')}
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
      >
        <KanbanSquare size={12} aria-hidden /> Board
      </Link>
      <Link
        to={scopedLink('search')}
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
      >
        <Activity size={12} aria-hidden /> Search
      </Link>
    </div>
  );
}

function KpiCard({
  Icon,
  label,
  value,
  hint,
  tone,
  bar,
}: {
  Icon: typeof Activity;
  label: string;
  value: string;
  hint?: string;
  tone: 'neutral' | 'positive' | 'warning' | 'danger';
  bar?: { pct: number; warn: boolean };
}) {
  const toneClass = {
    neutral: 'text-[var(--cos-text)]',
    positive: 'text-[var(--cos-ok)] glow-emerald',
    warning: 'text-[var(--cos-warn)] glow-amber',
    danger: 'text-[var(--cos-err)] glow-rose',
  }[tone];

  const borderClass = {
    neutral: 'border-white/5 shadow-white/5',
    positive: 'border-[var(--cos-ok)]  hover:border-[var(--cos-ok)]',
    warning: 'border-[var(--cos-warn)]  hover:border-[var(--cos-warn)]',
    danger: 'border-[var(--cos-err)]  hover:border-[var(--cos-err)]',
  }[tone];

  return (
    <section className={['glass-card rounded-xl border p-4 transition-all duration-300 relative overflow-hidden flex flex-col justify-between hover:-translate-y-0.5 hover:shadow-xl group', borderClass].join(' ')}>
      <div>
        <div className="mb-2.5 flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-semibold text-[var(--cos-muted)] group-hover:text-[var(--cos-text)] transition-colors">
          <Icon size={12} aria-hidden />
          {label}
        </div>
        <div className={['font-mono text-3xl font-extrabold leading-none', toneClass].join(' ')}>{value}</div>
      </div>
      <div className="mt-3">
        {hint && <div className="text-[10px] font-medium text-[var(--cos-faint)]">{hint}</div>}
        {bar && (
          <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-white/5">
            <div
              className={bar.warn ? 'h-full bg-[var(--cos-warn-tint)] shadow-[0_0_8px_rgba(245,158,11,0.5)]' : 'h-full bg-[var(--cos-accent)] shadow-[0_0_8px_var(--cos-accent)]'}
              style={{ width: `${Math.min(100, bar.pct)}%` }}
            />
          </div>
        )}
      </div>
    </section>
  );
}

function PanelCard({
  Icon,
  title,
  link,
  linkLabel,
  children,
}: {
  Icon: typeof Activity;
  title: string;
  link: string | null;
  linkLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="glass-card flex min-h-[280px] flex-col rounded-xl border border-white/5 p-4 transition-all duration-300 hover:shadow-2xl">
      <header className="mb-3.5 flex items-center gap-2 border-b border-white/5 pb-2.5">
        <Icon size={14} aria-hidden className="text-[var(--cos-muted)]" />
        <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--cos-text)]">
          {title}
        </h2>
        {link && (
          <Link to={link} className="ml-auto text-[10px] font-bold uppercase tracking-wider text-[var(--cos-accent)] hover:opacity-85">
            {linkLabel ?? 'open →'}
          </Link>
        )}
      </header>
      <div className="flex-1 min-h-0">{children}</div>
    </section>
  );
}

function ActionBadge({ action }: { action: string }) {
  const norm = action.toLowerCase();
  const pal = ACTION_BADGE[norm] ?? NEUTRAL_BADGE;
  return (
    <span
      className={['inline-block min-w-[3.25rem] shrink-0 whitespace-nowrap rounded px-1.5 py-0.5 text-center font-mono text-[9px] font-semibold uppercase tracking-wider', pal.bg, pal.text].join(' ')}
      title={action}
    >
      {'label' in pal && pal.label ? pal.label : norm}
    </span>
  );
}

function AgentBadge({ agent, active }: { agent: string; active: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-[var(--cos-border)] px-1 py-0.5 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">
      {active && (
        <span aria-hidden className="inline-block h-1 w-1 animate-pulse rounded-full bg-[var(--cos-ok-tint)]" />
      )}
      {agent}
    </span>
  );
}

function Badge({
  children,
  tone = 'muted',
}: {
  children: React.ReactNode;
  tone?: 'muted' | 'accent' | 'danger';
}) {
  const cls =
    tone === 'accent'
      ? 'bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]'
      : tone === 'danger'
      ? 'bg-[var(--cos-err-tint)] text-[var(--cos-err)]'
      : 'bg-[var(--cos-border)]/30 text-[var(--cos-muted)]';
  return (
    <span className={['rounded px-1 py-0.5 text-[9px] uppercase tracking-wider', cls].join(' ')}>{children}</span>
  );
}

function StatTile({
  label,
  value,
  subtitle,
  tone,
}: {
  label: string;
  value: number;
  subtitle?: string;
  tone?: 'neutral' | 'warning' | 'danger';
}) {
  const valueClass =
    tone === 'danger' && value > 0
      ? 'text-[var(--cos-err)]'
      : tone === 'warning'
      ? 'text-[var(--cos-warn)]'
      : 'text-[var(--cos-text)]';
  return (
    <div className="rounded-md border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5">
      <div className={['font-mono text-xl font-semibold leading-none', valueClass].join(' ')}>
        {value}
      </div>
      <div className="mt-1 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">{label}</div>
      {subtitle && <div className="text-[9px] text-[var(--cos-faint)]">{subtitle}</div>}
    </div>
  );
}

function Sparkbars({ data }: { data: { day: string; total: number }[] }) {
  const max = Math.max(0.0001, ...data.map((d) => d.total));
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="flex h-12 items-end gap-1">
      {data.map((d) => {
        const h = max > 0 ? Math.max(2, (d.total / max) * 44) : 2;
        const isToday = d.day === today;
        return (
          <div
            key={d.day}
            className="group relative flex flex-1 flex-col items-center"
            title={`${d.day} · $${d.total.toFixed(4)}`}
          >
            <div
              className={[
                'w-full rounded-t transition-colors',
                isToday ? 'bg-[var(--cos-accent)]' : 'bg-[var(--cos-border)]',
              ].join(' ')}
              style={{ height: `${h}px` }}
            />
            <span className="mt-1 font-mono text-[8px] text-[var(--cos-faint)]">
              {d.day.slice(-2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function EmptyState({
  icon,
  text,
  subtext,
}: {
  icon: string;
  text: string;
  subtext?: string;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-1 px-4 py-6 text-center">
      <span aria-hidden className="text-2xl text-[var(--cos-faint)]">
        {icon}
      </span>
      <p className="text-xs text-[var(--cos-muted)]">{text}</p>
      {subtext && <p className="text-[10px] text-[var(--cos-faint)]">{subtext}</p>}
    </div>
  );
}

function Skeleton({ rows }: { rows: number }) {
  return (
    <ul className="space-y-1.5">
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} className="h-6 animate-pulse rounded bg-[var(--cos-border)]/20" />
      ))}
    </ul>
  );
}
