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
import type { ContextAgent } from './dashboard/dashboard-types';
import { STATE_DOT, ageBadge, compactSession, rel, relIso } from './dashboard/dashboard-format';
import { useDashboardData } from './dashboard/useDashboardData';
import {
  ActionBadge,
  AgentBadge,
  Badge,
  DashboardHeader,
  EmptyState,
  KpiCard,
  PanelCard,
  QuickActions,
  Skeleton,
  Sparkbars,
  StatTile,
} from './dashboard/DashboardWidgets';

// ─────────────────────────────────────────────────────────────────────────
// Dashboard root
// ─────────────────────────────────────────────────────────────────────────

export function ContextPctBadge({ row }: { row?: ContextAgent }) {
  // Explicit unknown state — never 0%, never blank ( acceptance).
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
  const {
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
  } = useDashboardData();
  return (
    <div className="flex h-full flex-col overflow-auto bg-[var(--cos-bg)] p-6 cos-scroll">
      <DashboardHeader presentCount={presentCount} lastHook={presence.data?.last_hook ?? null} />

      {failedPanels.length > 0 && (
        <div
          role="alert"
          className="mb-4 rounded-lg border border-[var(--cos-err)]/40 bg-[var(--cos-err)]/10 px-3 py-2 text-[11px] text-[var(--cos-err)]"
        >
          Could not load: {failedPanels.map(([name]) => name).join(', ')} — {failedPanels[0][1].message}.
          Those tiles show stale or empty values, not real zeros.
        </div>
      )}

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
                        row={
                          s.context_pct != null
                            ? {
                                agent: s.agent,
                                session_id: s.session_id,
                                context_pct: s.context_pct,
                                used_tokens: s.used_tokens,
                                context_window: s.context_window,
                              }
                            : contextAgents.data?.agents.find(
                                (a) => a.session_id === s.session_id || a.agent === s.agent,
                              )
                        }
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
                    key={c.id}
                    className="flex items-center gap-2 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 text-[11px]"
                  >
                    <Badge tone={c.status === 'blocked' ? 'danger' : 'accent'}>
                      {c.status?.replace('_', ' ')}
                    </Badge>
                    <span className="truncate font-mono text-[10px] text-[var(--cos-muted)]">
                      {c.id}
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

