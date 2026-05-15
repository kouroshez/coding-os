import { useMemo } from 'react';
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
}
interface PresencePayload {
  agents: PresenceAgent[];
  agent_states: Record<string, string>;
  last_hook: HookEvent | null;
  current_chat_uuid: string | null;
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

const ACTION_BADGE: Record<string, { bg: string; text: string }> = {
  fire: { bg: 'bg-sky-500/15', text: 'text-sky-300' },
  block: { bg: 'bg-rose-500/15', text: 'text-rose-300' },
  warn: { bg: 'bg-amber-500/15', text: 'text-amber-300' },
  'stale-gate': { bg: 'bg-amber-500/15', text: 'text-amber-300' },
  skip: { bg: 'bg-zinc-500/15', text: 'text-zinc-400' },
  'skip-not-replace': { bg: 'bg-zinc-500/15', text: 'text-zinc-400' },
  pass: { bg: 'bg-emerald-500/15', text: 'text-emerald-300' },
  ok: { bg: 'bg-emerald-500/15', text: 'text-emerald-300' },
  entry: { bg: 'bg-violet-500/15', text: 'text-violet-300' },
  enter: { bg: 'bg-violet-500/15', text: 'text-violet-300' },
  dispatched: { bg: 'bg-cyan-500/15', text: 'text-cyan-300' },
  'session-end': { bg: 'bg-zinc-500/15', text: 'text-zinc-400' },
  posttooluse: { bg: 'bg-indigo-500/15', text: 'text-indigo-300' },
  pretooluse: { bg: 'bg-indigo-500/15', text: 'text-indigo-300' },
  'non-rename': { bg: 'bg-zinc-500/15', text: 'text-zinc-400' },
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

function compactSession(sid?: string | null): string {
  if (!sid) return '';
  if (sid.startsWith('ses-')) return sid.split('-').slice(-2).join('-');
  return sid.slice(0, 8);
}

// ─────────────────────────────────────────────────────────────────────────
// Dashboard root
// ─────────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const presence = useApiGet<PresencePayload>(
    ['presence-now'],
    '/api/presence/now',
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

  const liveAgents = Object.entries(presence.data?.agent_states ?? {}).filter(
    ([id, s]) => s !== 'offline' && id !== 'human',
  );
  const presentCount = liveAgents.length;

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
          hint={presentCount === 0 ? 'no agent running' : `of ${Object.keys(presence.data?.agent_states ?? {}).length}`}
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
        activeSessionAgent={liveAgents[0]?.[0] ?? null}
        activeSession={presence.data?.agents.find((a) => a.agent === liveAgents[0]?.[0])?.session_id ?? null}
      />

      {/* Main grid — 3 cols on xl, 2 on md */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <PanelCard
          Icon={Sparkles}
          title="Live agents"
          link={null}
        >
          {liveAgents.length === 0 ? (
            <EmptyState
              icon="●"
              text="No agent running right now"
              subtext="open a Claude / Codex / Cursor session in this repo to see live runtime."
            />
          ) : (
            <ul className="space-y-2">
              {liveAgents.map(([id, state]) => {
                const snap = presence.data?.agents.find((a) => a.agent === id);
                const dot = STATE_DOT[state] ?? STATE_DOT.offline;
                return (
                  <li
                    key={id}
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
                      <span className="font-semibold text-[var(--cos-text)]">{id}</span>
                      <Badge tone="muted">{dot.label}</Badge>
                      {snap?.model && (
                        <span className="ml-auto font-mono text-[10px] text-[var(--cos-faint)]">
                          {snap.model}
                        </span>
                      )}
                    </div>
                    {snap?.session_id && (
                      <div className="mt-1.5 truncate font-mono text-[10px] text-[var(--cos-muted)]">
                        {snap.session_id}
                      </div>
                    )}
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
                  </li>
                );
              })}
            </ul>
          )}
        </PanelCard>

        <PanelCard
          Icon={Zap}
          title="Recent hooks"
          link="/cognition?view=live"
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
          link="/cognition"
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
                      ? 'bg-rose-400'
                      : budgetPct > 50
                      ? 'bg-amber-400'
                      : 'bg-emerald-400',
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
          link="/cognition?view=chat"
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
                    to={`/cognition/${encodeURIComponent(c.session_id)}?view=chat`}
                    className="block rounded-md border border-transparent px-2 py-1.5 transition-colors hover:border-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/5"
                  >
                    <div className="truncate text-xs font-semibold text-[var(--cos-text)]">
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
          link="/cognition"
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
                    to={`/cognition/${encodeURIComponent(t.session_id)}`}
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
          link="/board"
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
              no tasks — create one in <Link to="/board" className="text-[var(--cos-accent)] hover:underline">Board</Link>.
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
        <h1 className="text-xl font-semibold text-[var(--cos-text)]">Mission Control</h1>
        <p className="mt-0.5 text-xs text-[var(--cos-muted)]">
          {presentCount > 0 ? (
            <>
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400 align-middle" />{' '}
              {presentCount} agent{presentCount === 1 ? '' : 's'} live · last hook{' '}
              <span className="font-mono text-[var(--cos-text)]">
                {lastHook?.hook ?? '—'}
              </span>{' '}
              <span className="text-[var(--cos-faint)]">{relIso(lastHook?.iso_ts)} ago</span>
            </>
          ) : (
            'idle · open Claude / Codex / Cursor to see live activity.'
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
}: {
  currentChat: string | null;
  activeSessionAgent: string | null;
  activeSession: string | null;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {currentChat && (
        <Link
          to={`/cognition/${encodeURIComponent(currentChat)}?view=chat`}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 px-3 py-1.5 text-[11px] font-semibold text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/20"
        >
          <MessageSquare size={12} aria-hidden /> Open current chat
        </Link>
      )}
      {activeSession && (
        <Link
          to={`/cognition/${encodeURIComponent(activeSession)}`}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
        >
          <Brain size={12} aria-hidden /> {activeSessionAgent ?? 'agent'} trace
        </Link>
      )}
      <Link
        to="/cognition?view=live"
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
      >
        <Zap size={12} aria-hidden /> Live hook stream
      </Link>
      <Link
        to="/board"
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
      >
        <KanbanSquare size={12} aria-hidden /> Board
      </Link>
      <Link
        to="/search"
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
    positive: 'text-emerald-300',
    warning: 'text-amber-300',
    danger: 'text-rose-300',
  }[tone];
  return (
    <section className="flex flex-col rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-3">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
        <Icon size={11} aria-hidden />
        {label}
      </div>
      <div className={['font-mono text-2xl font-semibold leading-none', toneClass].join(' ')}>{value}</div>
      {hint && <div className="mt-1 text-[10px] text-[var(--cos-faint)]">{hint}</div>}
      {bar && (
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-[var(--cos-border)]/30">
          <div
            className={bar.warn ? 'h-full bg-amber-400' : 'h-full bg-[var(--cos-accent)]'}
            style={{ width: `${Math.min(100, bar.pct)}%` }}
          />
        </div>
      )}
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
    <section className="flex min-h-[260px] flex-col rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-3">
      <header className="mb-2 flex items-center gap-2 border-b border-[var(--cos-border)]/60 pb-1.5">
        <Icon size={13} aria-hidden className="text-[var(--cos-muted)]" />
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-text)]">
          {title}
        </h2>
        {link && (
          <Link to={link} className="ml-auto text-[10px] text-[var(--cos-accent)] hover:underline">
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
  const pal = ACTION_BADGE[norm] ?? { bg: 'bg-[var(--cos-border)]/30', text: 'text-[var(--cos-muted)]' };
  return (
    <span
      className={['w-16 shrink-0 rounded px-1 py-0.5 text-center font-mono text-[9px] font-semibold uppercase tracking-wider', pal.bg, pal.text].join(' ')}
      title={action}
    >
      {norm.slice(0, 9)}
    </span>
  );
}

function AgentBadge({ agent, active }: { agent: string; active: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-[var(--cos-border)] px-1 py-0.5 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">
      {active && (
        <span aria-hidden className="inline-block h-1 w-1 animate-pulse rounded-full bg-emerald-400" />
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
      ? 'bg-rose-500/15 text-rose-300'
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
      ? 'text-rose-300'
      : tone === 'warning'
      ? 'text-amber-300'
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
