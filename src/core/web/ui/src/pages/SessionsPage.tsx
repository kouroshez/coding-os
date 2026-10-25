import { useMemo } from 'react';
import { useApiGet } from '@/lib/hooks';
import { modelLabel } from '@/lib/presence';
import { PageShell, PageHeader } from '@/layout/HubPrimitives';
import { ContextPctBadge } from './DashboardPage';
import type { ActiveSession } from './dashboard/dashboard-types';
import { STATE_DOT } from './dashboard/dashboard-format';

interface ActivePayload {
  sessions: ActiveSession[];
  counts: Record<string, number>;
  now: number;
}

interface HistorySession {
  agent: string;
  session_id: string;
  display_name: string;
  started_at?: number | null;
  last_prompt_at?: number | null;
  last_tool_at?: number | null;
  last_stop_at?: number | null;
  ended_at?: number | null;
  source?: string;
}
interface HistoryPayload {
  sessions: HistorySession[];
}

const STATE_ORDER = ['active', 'present', 'idle', 'offline', 'ended'];

function relTime(epoch: number | null | undefined, now: number): string {
  if (!epoch) return '—';
  const diff = Math.max(0, now - epoch);
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function lastActivity(
  s: Pick<HistorySession, 'last_prompt_at' | 'last_tool_at' | 'last_stop_at' | 'ended_at'>,
): number | null {
  return Math.max(s.last_tool_at ?? 0, s.last_prompt_at ?? 0, s.last_stop_at ?? 0, s.ended_at ?? 0) || null;
}

function Th({ children, end }: { children: React.ReactNode; end?: boolean }) {
  return <th className={`px-4 py-2 font-normal ${end ? 'text-end' : 'text-start'}`}>{children}</th>;
}

function Card({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/50">
      <header className="flex items-center gap-2 border-b border-[var(--cos-border)]/60 px-4 py-3">
        <h2 className="text-sm font-semibold text-[var(--cos-text)]">{title}</h2>
        <span className="rounded-full bg-[var(--cos-panel)] px-2 font-mono text-[10px] text-[var(--cos-muted)]">
          {count}
        </span>
      </header>
      {children}
    </section>
  );
}

function Note({ children, tone }: { children: React.ReactNode; tone?: 'err' }) {
  return (
    <p
      className={`px-4 py-8 text-center text-xs ${tone === 'err' ? 'text-[var(--cos-err)]' : 'text-[var(--cos-muted)]'}`}
    >
      {children}
    </p>
  );
}

export default function SessionsPage() {
  const active = useApiGet<ActivePayload>(['sessions-active'], '/api/sessions/active', undefined, {
    refetchIntervalMs: 5000,
  });
  const history = useApiGet<HistoryPayload>(['sessions-history'], '/api/observability/sessions');

  const now = active.data?.now ?? Math.floor(Date.now() / 1000);
  const counts = active.data?.counts ?? {};
  const liveRows = useMemo(() => active.data?.sessions ?? [], [active.data]);

  // History lists sessions that left a presence record; a trace file with no
  // session behind it is a test or dispatch artefact, not a session anyone ran.
  const historyRows = useMemo(() => {
    const liveIds = new Set(liveRows.map((s) => s.session_id));
    return (history.data?.sessions ?? [])
      .filter((s) => s.source !== 'trace-only' && !liveIds.has(s.session_id))
      .sort((a, b) => (lastActivity(b) ?? 0) - (lastActivity(a) ?? 0));
  }, [liveRows, history.data]);

  return (
    <PageShell>
      <PageHeader
        title="Sessions"
        subtitle="Every agent session in this project: who is running, on which model, and how full its context is."
        right={
          <div className="flex flex-wrap gap-2">
            {STATE_ORDER.filter((state) => counts[state]).map((state) => (
              <span
                key={state}
                className="inline-flex items-center gap-1.5 rounded-full border border-[var(--cos-border)] bg-[var(--cos-panel)]/70 px-3 py-1 text-[11px]"
              >
                <span
                  aria-hidden
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: (STATE_DOT[state] ?? STATE_DOT.offline).color }}
                />
                <span className="capitalize text-[var(--cos-muted)]">{state}</span>
                <span className="font-mono tabular-nums text-[var(--cos-text)]">{counts[state]}</span>
              </span>
            ))}
          </div>
        }
      />

      <Card title="Running" count={liveRows.length}>
        {active.isLoading ? (
          <Note>Loading sessions…</Note>
        ) : active.error ? (
          <Note tone="err">Could not load sessions: {active.error.message}</Note>
        ) : liveRows.length === 0 ? (
          <Note>No agent is running in this project.</Note>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] font-mono uppercase tracking-[0.14em] text-[var(--cos-faint)]">
                  <Th>Agent</Th>
                  <Th>Model</Th>
                  <Th>State</Th>
                  <Th>Context</Th>
                  <Th>Started</Th>
                  <Th>Last tool</Th>
                  <Th end>Last prompt</Th>
                </tr>
              </thead>
              <tbody>
                {liveRows.map((s) => {
                  const dot = STATE_DOT[s.state] ?? STATE_DOT.offline;
                  return (
                    <tr key={`${s.agent}:${s.session_id}`} className="border-t border-[var(--cos-border)]/60">
                      <td className="px-4 py-2.5">
                        <span className="flex items-center gap-2">
                          <span
                            aria-hidden
                            className={`h-1.5 w-1.5 rounded-full ${dot.pulse ? 'animate-pulse' : ''}`}
                            style={{ background: dot.color }}
                          />
                          <span className="text-sm text-[var(--cos-text)]">{s.agent}</span>
                          {s.is_current && (
                            <span className="rounded-full bg-[var(--accent)]/15 px-1.5 text-[9px] font-semibold uppercase text-[var(--accent)]">
                              this
                            </span>
                          )}
                        </span>
                        <span className="block ps-3.5 font-mono text-[10px] text-[var(--cos-faint)]">
                          {s.session_id}
                          {s.pid ? ` · pid ${s.pid}` : ''}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-[var(--cos-muted)]">{s.model ? modelLabel(s.model) : '—'}</td>
                      <td className="px-4 py-2.5 capitalize text-[var(--cos-muted)]">{dot.label}</td>
                      <td className="px-4 py-2.5">
                        <ContextPctBadge
                          row={{
                            agent: s.agent,
                            context_pct: s.context_pct ?? null,
                            used_tokens: s.used_tokens,
                            context_window: s.context_window,
                          }}
                        />
                      </td>
                      <td className="px-4 py-2.5 text-[var(--cos-muted)]">{relTime(s.started_at, now)}</td>
                      <td className="px-4 py-2.5 text-[var(--cos-muted)]">{relTime(s.last_tool_at, now)}</td>
                      <td className="px-4 py-2.5 text-end text-[var(--cos-muted)]">
                        {relTime(s.last_prompt_at, now)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="History" count={historyRows.length}>
        {history.isLoading ? (
          <Note>Loading history…</Note>
        ) : history.error ? (
          <Note tone="err">Could not load history: {history.error.message}</Note>
        ) : historyRows.length === 0 ? (
          <Note>No earlier sessions recorded yet.</Note>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] font-mono uppercase tracking-[0.14em] text-[var(--cos-faint)]">
                <Th>Session</Th>
                <Th>Agent</Th>
                <Th>Started</Th>
                <Th end>Last activity</Th>
              </tr>
            </thead>
            <tbody>
              {historyRows.map((s) => (
                <tr key={`${s.agent}:${s.session_id}`} className="border-t border-[var(--cos-border)]/60">
                  <td className="px-4 py-2.5">
                    <span className="block text-sm text-[var(--cos-text)]">{s.display_name}</span>
                    <span className="block font-mono text-[10px] text-[var(--cos-faint)]">{s.session_id}</span>
                  </td>
                  <td className="px-4 py-2.5 text-[var(--cos-muted)]">{s.agent}</td>
                  <td className="px-4 py-2.5 text-[var(--cos-muted)]">{relTime(s.started_at, now)}</td>
                  <td className="px-4 py-2.5 text-end text-[var(--cos-muted)]">{relTime(lastActivity(s), now)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </PageShell>
  );
}
