import { Link } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { useScopedLink } from '@/lib/use-scoped-link';

interface UnifiedAgent {
  agent: string;
  session_id?: string | null;
  sdk_uuid?: string | null;
  model?: string | null;
  gate?: string | null;
  task?: string | null;
  skill_active?: string | null;
  role?: string | null;
  chain?: string[];
  state?: string | null;
  context_pct?: number | null;
}

const STATE_DOT: Record<string, string> = {
  active: '#16a34a',
  working: '#16a34a',
  present: '#fbbf24',
  idle: '#fbbf24',
  offline: '#6b7280',
};

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt>{k}</dt>
      <dd className="truncate font-mono text-[var(--cos-text)]">{v}</dd>
    </div>
  );
}

/** Inline live-agents section for the home page (TASK-194) — one card per
 *  live agent from the unified /api/presence/agents endpoint, click-through
 *  to its chat (when an sdk_uuid is known) or the live cognition view. */
export default function LiveAgentsPanel() {
  const { scopedLink } = useScopedLink();
  const { data } = useApiGet<{ agents: UnifiedAgent[] }>(
    ['presence-agents-home'],
    '/api/presence/agents',
    undefined,
    { refetchIntervalMs: 4000 },
  );
  const agents = (data?.agents ?? []).filter((a) => a.state && a.state !== 'offline');
  if (agents.length === 0) return null;

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-[11px] font-bold tracking-widest text-[var(--cos-muted)] uppercase">
        live agents
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((a) => {
          const dot = STATE_DOT[a.state ?? 'offline'] ?? '#6b7280';
          const target = a.sdk_uuid
            ? scopedLink('cognition', `${encodeURIComponent(a.sdk_uuid)}?view=chat`)
            : scopedLink('cognition', '?view=live');
          return (
            <Link
              key={a.agent}
              to={target}
              className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-3 transition-colors hover:border-[var(--cos-accent)]"
            >
              <div className="mb-2 flex items-center gap-2">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} aria-hidden />
                <span className="text-xs font-semibold text-[var(--cos-text)]">{a.agent}</span>
                <span className="ml-auto text-[10px] text-[var(--cos-muted)]">{a.state}</span>
              </div>
              <dl className="space-y-0.5 text-[10px] text-[var(--cos-muted)]">
                <Row k="model" v={a.model ?? '—'} />
                <Row k="gate" v={a.gate ?? '—'} />
                {a.role && <Row k="role" v={a.role} />}
                <Row k="context" v={a.context_pct != null ? `${a.context_pct}%` : 'N/A'} />
                {a.task && <Row k="task" v={a.task} />}
              </dl>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
