import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';

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
  presence_file: string;
}
interface ActivePayload {
  sessions: ActiveSession[];
  counts: Record<string, number>;
  now: number;
  ttl_s: number;
  state_dir: string;
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
  is_active?: boolean;
  has_trace?: boolean;
  source?: string;
  trace_path?: string | null;
  size_bytes?: number | null;
  modified_ts?: number | null;
}
interface HistoryPayload {
  sessions: HistorySession[];
  count: number;
  active_count: number;
  trace_count: number;
}

const STATE_COLORS: Record<string, string> = {
  active: '#16a34a',
  present: '#22c55e',
  idle: '#fbbf24',
  offline: '#9ea4ae',
  ended: '#6b7280',
};

function relTime(epoch: number | null | undefined, now: number): string {
  if (!epoch) return '—';
  const diff = Math.max(0, now - epoch);
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export default function SessionsPage() {
  const navigate = useNavigate();
  const active = useApiGet<ActivePayload>(['sessions-active'], '/api/sessions/active', undefined, {
    refetchIntervalMs: 5000,
  });
  const history = useApiGet<HistoryPayload>(['sessions-history'], '/api/observability/sessions');

  const now = active.data?.now ?? Math.floor(Date.now() / 1000);
  const counts = active.data?.counts ?? {};

  const historyOnly = useMemo(() => {
    // Exclude rows already shown in Active panel — match on session_id.
    const activeIds = new Set((active.data?.sessions ?? []).map((s) => s.session_id));
    return (history.data?.sessions ?? []).filter((s) => !activeIds.has(s.session_id));
  }, [active.data, history.data]);

  const openTrace = (sid: string) => {
    navigate(`/cognition/${encodeURIComponent(sid)}`);
  };

  return (
    <PageShell>
      <PageHeader
        eyebrow={<StatusPill label="sessions · agent presence" />}
        title="Sessions"
        subtitle="Live agent presence + history. Click a row to replay its cognition trace."
        right={
          <div className="flex flex-wrap gap-2">
            {Object.entries(counts).map(([state, n]) => (
              <span
                key={state}
                className="inline-flex items-center gap-1.5 rounded-full border border-[var(--cos-border)] bg-[var(--cos-panel)]/70 px-3 py-1 text-[11px] font-mono backdrop-blur"
              >
                <span
                  aria-hidden
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: STATE_COLORS[state] ?? '#9ea4ae' }}
                />
                <span className="uppercase tracking-wider text-[var(--cos-muted)]">{state}</span>
                <span className="tabular-nums text-[var(--cos-text)]">{n}</span>
              </span>
            ))}
          </div>
        }
      />

      <section className="mb-4 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] p-2">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
          Active presence ({active.data?.sessions.length ?? 0})
        </h3>
        {active.isLoading && <p className="text-xs text-[var(--cos-muted)]">loading…</p>}
        {active.error && <p className="text-xs text-rose-400">{active.error.message}</p>}
        {active.data && active.data.sessions.length === 0 && (
          <p className="text-xs text-[var(--cos-muted)]">no agents present.</p>
        )}
        {active.data && active.data.sessions.length > 0 && (
          <table className="w-full border-collapse text-[11px]">
            <thead className="text-left text-[var(--cos-muted)]">
              <tr>
                <th className="py-1 pr-2">state</th>
                <th className="py-1 pr-2">agent</th>
                <th className="py-1 pr-2">session</th>
                <th className="py-1 pr-2">pid</th>
                <th className="py-1 pr-2">last tool</th>
                <th className="py-1 pr-2">last prompt</th>
              </tr>
            </thead>
            <tbody>
              {active.data.sessions.map((s) => (
                <tr
                  key={s.session_id}
                  className="cursor-pointer hover:bg-[var(--cos-grain)]"
                  onClick={() => openTrace(s.session_id)}
                >
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2">
                    <span
                      aria-hidden
                      className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
                      style={{ background: STATE_COLORS[s.state] ?? '#9ea4ae' }}
                    />
                    {s.state}
                  </td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2 font-mono">{s.agent}</td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2 font-mono text-[var(--cos-muted)]">
                    {s.session_id}
                  </td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2">{s.pid ?? '—'}</td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2">{relTime(s.last_tool_at, now)}</td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2">{relTime(s.last_prompt_at, now)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] p-2">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
          History ({historyOnly.length})
        </h3>
        {history.isLoading && <p className="text-xs text-[var(--cos-muted)]">loading…</p>}
        {history.error && <p className="text-xs text-rose-400">{history.error.message}</p>}
        {history.data && historyOnly.length === 0 && (
          <p className="text-xs text-[var(--cos-muted)]">no past sessions on disk.</p>
        )}
        {historyOnly.length > 0 && (
          <table className="w-full border-collapse text-[11px]">
            <thead className="text-left text-[var(--cos-muted)]">
              <tr>
                <th className="py-1 pr-2">name</th>
                <th className="py-1 pr-2">agent</th>
                <th className="py-1 pr-2">source</th>
                <th className="py-1 pr-2">trace size</th>
                <th className="py-1 pr-2">last activity</th>
              </tr>
            </thead>
            <tbody>
              {historyOnly.map((s) => (
                <tr
                  key={`${s.agent}:${s.session_id}`}
                  className="cursor-pointer hover:bg-[var(--cos-grain)]"
                  onClick={() => openTrace(s.session_id)}
                >
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2 font-mono">{s.display_name}</td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2 font-mono">{s.agent}</td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2 text-[var(--cos-muted)]">{s.source ?? '—'}</td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2">
                    {s.size_bytes != null ? `${Math.ceil(s.size_bytes / 1024)}kb` : '—'}
                  </td>
                  <td className="border-t border-[var(--cos-border)] py-1 pr-2">
                    {relTime(
                      s.last_tool_at ?? s.last_prompt_at ?? s.modified_ts ?? s.started_at ?? null,
                      now,
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </PageShell>
  );
}
