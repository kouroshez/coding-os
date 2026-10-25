import { Link } from 'react-router-dom';
import { ArrowRight, Brain, KanbanSquare, MessageSquare, Package, Users } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { PageHeader, PageShell } from '@/layout/HubPrimitives';
import { modelLabel } from '@/lib/presence';
import { useScopedLink } from '@/lib/use-scoped-link';
import type { ActiveSession, ContextAgent } from './dashboard/dashboard-types';
import { STATE_DOT, ageBadge, compactSession, rel } from './dashboard/dashboard-format';
import { useDashboardData } from './dashboard/useDashboardData';

export function ContextPctBadge({ row }: { row?: ContextAgent }) {
  // Explicit unknown state — never 0%, never blank.
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
  const tone = pct >= 85 ? 'var(--cos-err)' : pct >= 60 ? 'var(--cos-warn)' : 'var(--cos-ok)';
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

const BOARD_STATS: Array<[string, string]> = [
  ['in_progress', 'In progress'],
  ['testing', 'Testing'],
  ['blocked', 'Blocked'],
];

function Stat({
  to,
  Icon,
  label,
  value,
  hint,
  tone,
}: {
  to: string;
  Icon: LucideIcon;
  label: string;
  value: string;
  hint: string;
  tone?: 'ok' | 'warn' | 'err';
}) {
  const hintTone =
    tone === 'err'
      ? 'text-[var(--cos-err)]'
      : tone === 'warn'
        ? 'text-[var(--cos-warn)]'
        : 'text-[var(--cos-muted)]';
  return (
    <Link
      to={to}
      className="group flex flex-col gap-1 p-5 transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]"
    >
      <span className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.16em] text-[var(--cos-muted)]">
        <Icon size={12} aria-hidden />
        {label}
        <ArrowRight
          size={12}
          aria-hidden
          className="ms-auto opacity-0 transition-opacity group-hover:opacity-100"
        />
      </span>
      <span className="text-2xl font-semibold tabular-nums text-[var(--cos-text)]">{value}</span>
      <span className={`truncate text-xs ${hintTone}`}>{hint}</span>
    </Link>
  );
}

function Panel({
  title,
  link,
  linkLabel,
  children,
}: {
  title: string;
  link: string;
  linkLabel: string;
  children: React.ReactNode;
}) {
  return (
    <section className="self-start overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/50">
      <header className="flex items-center justify-between border-b border-[var(--cos-border)]/60 px-4 py-3">
        <h2 className="text-sm font-semibold text-[var(--cos-text)]">{title}</h2>
        <Link to={link} className="text-xs text-[var(--accent)] hover:underline">
          {linkLabel}
        </Link>
      </header>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-4 py-8 text-center text-xs text-[var(--cos-muted)]">{children}</p>;
}

function SessionRow({ session }: { session: ActiveSession }) {
  const dot = STATE_DOT[session.state] ?? STATE_DOT.offline;
  const lastActivity = Math.max(session.last_tool_at ?? 0, session.last_prompt_at ?? 0) || null;
  return (
    <tr className="border-t border-[var(--cos-border)]/60 first:border-t-0">
      <td className="px-4 py-2.5">
        <span className="flex items-center gap-2">
          <span
            aria-hidden
            className={`h-1.5 w-1.5 rounded-full ${dot.pulse ? 'animate-pulse' : ''}`}
            style={{ background: dot.color }}
          />
          <span className="text-sm text-[var(--cos-text)]">{session.agent}</span>
          {session.is_current && (
            <span className="rounded-full bg-[var(--accent)]/15 px-1.5 text-[9px] font-semibold uppercase text-[var(--accent)]">
              this
            </span>
          )}
        </span>
        <span className="block ps-3.5 font-mono text-[10px] text-[var(--cos-faint)]">
          {compactSession(session.session_id)}
        </span>
      </td>
      <td className="px-2 py-2.5 text-xs text-[var(--cos-muted)]">
        {session.model ? modelLabel(session.model) : '—'}
      </td>
      <td className="px-2 py-2.5 text-xs capitalize text-[var(--cos-muted)]">{dot.label}</td>
      <td className="px-2 py-2.5">
        <ContextPctBadge
          row={{
            agent: session.agent,
            context_pct: session.context_pct ?? null,
            used_tokens: session.used_tokens,
            context_window: session.context_window,
          }}
        />
      </td>
      <td className="px-4 py-2.5 text-end font-mono text-[10px] text-[var(--cos-faint)]">
        {lastActivity ? ageBadge(lastActivity) : '—'}
      </td>
    </tr>
  );
}

export default function DashboardPage() {
  const { scopedLink } = useScopedLink();
  const {
    activeCards,
    cards,
    chats,
    failedPanels,
    installed,
    liveCount,
    memory,
    sessionRows,
    statusCounts,
    wipCap,
  } = useDashboardData();

  const lint = memory.data?.lint;
  const memoryTone = lint?.errors.length ? 'err' : lint?.warnings.length ? 'warn' : undefined;
  const memoryHint = !memory.data?.present
    ? 'no .agents/memory yet'
    : lint?.errors.length
      ? `${lint.errors.length} lint error${lint.errors.length === 1 ? '' : 's'}`
      : lint?.warnings.length
        ? `${lint.warnings.length} lint warning${lint.warnings.length === 1 ? '' : 's'}`
        : 'lint healthy';
  const inProgress = statusCounts.in_progress ?? 0;
  const known = (n: number | null) => (n === null ? '—' : String(n));

  return (
    <PageShell>
      <PageHeader
        title="Overview"
        subtitle="What the agents in this project are doing, and what they have to work with."
      />

      {failedPanels.length > 0 && (
        <div
          role="alert"
          className="mb-4 rounded-xl border border-[var(--cos-err)]/40 bg-[var(--cos-err-tint)] px-4 py-2 text-xs text-[var(--cos-err)]"
        >
          Could not load {failedPanels.map(([name]) => name).join(', ')}: {failedPanels[0][1].message}.
          Those panels show stale or empty values, not real zeros.
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 divide-[var(--cos-border)]/60 overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/50 md:grid-cols-4 md:divide-x">
        <Stat
          to={scopedLink('diagnostics', 'sessions')}
          Icon={Users}
          label="Sessions"
          value={String(liveCount)}
          hint={`live · ${sessionRows.length} tracked`}
        />
        <Stat
          to={scopedLink('workspace', 'board')}
          Icon={KanbanSquare}
          label="Tasks"
          value={String(inProgress)}
          hint={`in progress${wipCap ? ` of ${wipCap}` : ''} · ${statusCounts.testing ?? 0} testing · ${cards.length} open`}
          tone={wipCap > 0 && inProgress > wipCap ? 'warn' : undefined}
        />
        <Stat
          to={scopedLink('workspace', 'memory')}
          Icon={Brain}
          label="Memory"
          value={String(memory.data?.memories?.length ?? 0)}
          hint={memoryHint}
          tone={memoryTone}
        />
        <Stat
          to={scopedLink('config')}
          Icon={Package}
          label="Installed"
          value={`${known(installed.skills)} skills`}
          hint={`${known(installed.stacks)} stack · ${known(installed.mcp)} MCP · ${known(installed.adapters)} adapters`}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          <Panel title="Sessions" link={scopedLink('diagnostics', 'sessions')} linkLabel="All sessions →">
            {sessionRows.length === 0 ? (
              <Empty>No agent has run in this project yet.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-start">
                  <thead>
                    <tr className="text-[10px] font-mono uppercase tracking-[0.14em] text-[var(--cos-faint)]">
                      <th className="px-4 py-2 text-start font-normal">Agent</th>
                      <th className="px-2 py-2 text-start font-normal">Model</th>
                      <th className="px-2 py-2 text-start font-normal">State</th>
                      <th className="px-2 py-2 text-start font-normal">Context</th>
                      <th className="px-4 py-2 text-end font-normal">Last activity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessionRows.map((session) => (
                      <SessionRow key={`${session.agent}:${session.session_id}`} session={session} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title="Recent chats" link={scopedLink('workspace', 'chat')} linkLabel="Open chat →">
            {(chats.data?.sessions ?? []).length === 0 ? (
              <Empty>No chats yet. Start one from the Chat tab.</Empty>
            ) : (
              <ul className="divide-y divide-[var(--cos-border)]/60">
                {(chats.data?.sessions ?? []).map((chat) => (
                  <li key={chat.session_id}>
                    <Link
                      to={scopedLink('workspace', `chat/${encodeURIComponent(chat.session_id)}`)}
                      className="flex items-center gap-3 px-4 py-2.5 hover:bg-white/5"
                    >
                      <MessageSquare size={13} aria-hidden className="shrink-0 text-[var(--cos-muted)]" />
                      <span className="min-w-0 flex-1 truncate text-sm text-[var(--cos-text)]">
                        {chat.custom_title || chat.summary || chat.first_prompt || chat.session_id}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] text-[var(--cos-faint)]">
                        {rel(chat.last_modified)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <Panel title="Board" link={scopedLink('workspace', 'board')} linkLabel="Open board →">
          <dl className="grid grid-cols-3 gap-px border-b border-[var(--cos-border)]/60 bg-[var(--cos-border)]/40">
            {BOARD_STATS.map(([status, label]) => (
              <div key={status} className="bg-[var(--cos-panel)] px-4 py-3">
                <dt className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">{label}</dt>
                <dd className="text-lg font-semibold tabular-nums text-[var(--cos-text)]">
                  {statusCounts[status] ?? 0}
                </dd>
              </div>
            ))}
          </dl>
          {activeCards.length === 0 ? (
            <Empty>Nothing in progress or testing.</Empty>
          ) : (
            <ul className="divide-y divide-[var(--cos-border)]/60">
              {activeCards.map((card) => (
                <li key={card.id} className="px-4 py-2.5">
                  <span className="flex items-baseline gap-2">
                    <span className="font-mono text-[10px] text-[var(--cos-faint)]">{card.id}</span>
                    <span className="rounded-full bg-[var(--cos-panel)] px-1.5 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">
                      {card.status === 'in_progress' ? 'in progress' : card.status}
                    </span>
                  </span>
                  <span className="line-clamp-2 text-sm text-[var(--cos-text)]">{card.title}</span>
                  {card.status_dwell_human && (
                    <span className="text-[10px] text-[var(--cos-faint)]">for {card.status_dwell_human}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </PageShell>
  );
}
