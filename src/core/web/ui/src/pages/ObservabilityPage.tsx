import { useState } from 'react';
import HookStream from '@/features/observability/HookStream';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';
import { useApiGet } from '@/lib/hooks';

type Tab = 'stream' | 'registry' | 'timeline' | 'standup';

interface HookRow {
  name: string | null;
  event: string | null;
  matcher: string | null;
  category: string | null;
  phase: string | null;
  adapter_scope: string | null;
  script: string | null;
}
interface HookListPayload {
  hooks: HookRow[];
  count: number;
}

interface TimelineEvent {
  source: string;
  kind: string;
  status?: string | null;
  ts?: number | null;
  iso_ts?: string | null;
  session_id?: string | null;
  agent?: string | null;
  summary: string;
  data?: Record<string, unknown> | null;
}
interface TimelinePayload {
  events: TimelineEvent[];
  count: number;
  session_id: string | null;
  sources: string[];
}

interface WipPayload {
  counts: Record<string, number>;
  caps: Record<string, number>;
  violations: unknown[];
  over_cap: boolean;
}
interface DailyTaskRow {
  task_id?: string;
  title?: string;
  status?: string;
  swimlane?: string;
}
interface DailyPayload {
  yesterday: DailyTaskRow[];
  in_progress: DailyTaskRow[];
  blockers: DailyTaskRow[];
  wip: WipPayload;
}
interface RetroPayload {
  completed_count: number;
  cycle_time_avg_minutes: number | null;
  emergency_count: number;
  swimlane_throughput: Record<string, number>;
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'stream', label: 'Hook stream' },
  { id: 'registry', label: 'Hook registry' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'standup', label: 'Board standup' },
];

export default function ObservabilityPage() {
  const [tab, setTab] = useState<Tab>('stream');
  return (
    <PageShell>
      <PageHeader
        eyebrow={<StatusPill label="observability · live hook stream" dotColor="bg-[var(--cos-warn-tint)]" />}
        title="Observability"
        subtitle="Live hook stream, hook registry, audit timeline, and 7-day stand-up rollup."
      />
      <nav
        className="mb-5 flex flex-wrap gap-2 rounded-full border border-[var(--cos-border)] bg-[var(--cos-panel)]/70 p-1 backdrop-blur"
        aria-label="Observability tabs"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            aria-pressed={tab === t.id}
            className={[
              'rounded-full px-4 py-1.5 text-xs font-medium transition-all',
              tab === t.id
                ? 'bg-[var(--accent)] text-[var(--cos-bg)] shadow-md shadow-[var(--accent)]/20'
                : 'text-[var(--cos-muted)] hover:bg-[var(--cos-panel)] hover:text-[var(--cos-text)]',
            ].join(' ')}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div className="min-h-[60vh] rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 overflow-hidden">
        {tab === 'stream' && <HookStream />}
        {tab === 'registry' && <HookRegistry />}
        {tab === 'timeline' && <Timeline />}
        {tab === 'standup' && <Standup />}
      </div>
    </PageShell>
  );
}

function HookRegistry() {
  const q = useApiGet<HookListPayload>(['hooks-list'], '/api/hooks/list');
  return (
    <div className="h-full overflow-auto p-3 text-xs">
      <h2 className="mb-2 text-sm font-semibold text-[var(--cos-text)]">Hook registry</h2>
      {q.isLoading && <p className="text-[var(--cos-muted)]">loading…</p>}
      {q.error && <p className="text-[var(--cos-err)]">{q.error.message}</p>}
      {q.data && (
        <>
          <p className="mb-2 text-[10px] text-[var(--cos-muted)]">{q.data.count} hooks registered.</p>
          <table className="w-full border-collapse text-[11px]">
            <thead className="text-left text-[var(--cos-muted)]">
              <tr>
                <th className="border-b border-[var(--cos-border)] py-1 pr-2">name</th>
                <th className="border-b border-[var(--cos-border)] py-1 pr-2">event</th>
                <th className="border-b border-[var(--cos-border)] py-1 pr-2">matcher</th>
                <th className="border-b border-[var(--cos-border)] py-1 pr-2">phase</th>
                <th className="border-b border-[var(--cos-border)] py-1 pr-2">category</th>
                <th className="border-b border-[var(--cos-border)] py-1 pr-2">scope</th>
              </tr>
            </thead>
            <tbody>
              {q.data.hooks.map((h, i) => (
                <tr key={`${h.name}-${i}`} className="hover:bg-[var(--cos-grain)]">
                  <td className="border-b border-[var(--cos-border)] py-1 pr-2 font-mono">{h.name ?? '—'}</td>
                  <td className="border-b border-[var(--cos-border)] py-1 pr-2">{h.event ?? '—'}</td>
                  <td className="border-b border-[var(--cos-border)] py-1 pr-2 font-mono text-[var(--cos-muted)]">{h.matcher ?? '*'}</td>
                  <td className="border-b border-[var(--cos-border)] py-1 pr-2">{h.phase ?? '—'}</td>
                  <td className="border-b border-[var(--cos-border)] py-1 pr-2">{h.category ?? '—'}</td>
                  <td className="border-b border-[var(--cos-border)] py-1 pr-2">{h.adapter_scope ?? 'all'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function Timeline() {
  const [sid, setSid] = useState('');
  const params: Record<string, unknown> = { limit: 200 };
  if (sid.trim()) params.session_id = sid.trim();
  const q = useApiGet<TimelinePayload>(['observability-timeline', sid], '/api/observability/timeline', params);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-2">
        <label className="text-[10px] text-[var(--cos-muted)]">session</label>
        <input
          type="search"
          value={sid}
          onChange={(e) => setSid(e.target.value)}
          placeholder="ses-claude-... (blank = all)"
          className="w-72 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 text-[11px]"
        />
        <span className="text-[10px] text-[var(--cos-muted)]">{q.data?.count ?? 0} events</span>
      </div>
      <ol className="cos-scroll flex-1 overflow-auto p-2 text-[11px]">
        {q.isLoading && <li className="p-4 text-[var(--cos-muted)]">loading…</li>}
        {q.error && <li className="p-4 text-[var(--cos-err)]">{q.error.message}</li>}
        {q.data?.events.map((ev, i) => (
          <li
            key={`${ev.iso_ts ?? ev.ts ?? i}-${ev.kind}-${i}`}
            className="mb-1 flex items-center gap-2 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1"
          >
            <span className="w-16 shrink-0 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">{ev.source}</span>
            <span className="w-44 shrink-0 truncate font-mono">{ev.kind}</span>
            <span className="w-16 shrink-0 text-[10px] text-[var(--cos-muted)]">{ev.status ?? '—'}</span>
            <span className="flex-1 truncate">{ev.summary}</span>
            <span className="shrink-0 font-mono text-[10px] text-[var(--cos-faint)]">{ev.agent ?? ''}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Standup() {
  const daily = useApiGet<DailyPayload>(['board-daily'], '/api/board/daily', { since: '24h' });
  const wip = useApiGet<WipPayload>(['board-wip'], '/api/board/wip');
  const retro = useApiGet<RetroPayload>(['board-retro'], '/api/board/retro', { since: '7d' });
  return (
    <div className="grid h-full grid-cols-1 gap-3 overflow-auto p-3 md:grid-cols-3">
      <Card title="Daily — yesterday" loading={daily.isLoading} error={daily.error}>
        <TaskList rows={daily.data?.yesterday ?? []} />
      </Card>
      <Card title="In progress" loading={daily.isLoading} error={daily.error}>
        <TaskList rows={daily.data?.in_progress ?? []} />
      </Card>
      <Card title="Blockers" loading={daily.isLoading} error={daily.error}>
        <TaskList rows={daily.data?.blockers ?? []} />
      </Card>
      <Card title="WIP caps" loading={wip.isLoading} error={wip.error}>
        {wip.data && (
          <ul className="space-y-1">
            {Object.entries(wip.data.counts).map(([col, n]) => {
              const cap = wip.data?.caps[col] ?? 0;
              const over = cap > 0 && n > cap;
              return (
                <li key={col} className="flex items-center justify-between">
                  <span className="font-mono">{col}</span>
                  <span className={over ? 'text-[var(--cos-err)]' : 'text-[var(--cos-muted)]'}>
                    {n} / {cap}
                  </span>
                </li>
              );
            })}
            {wip.data.over_cap && <li className="text-[var(--cos-err)]">⚠ over-cap</li>}
          </ul>
        )}
      </Card>
      <Card title="Retro (7d)" loading={retro.isLoading} error={retro.error}>
        {retro.data && (
          <dl className="space-y-1">
            <Row k="completed" v={String(retro.data.completed_count)} />
            <Row k="cycle avg" v={retro.data.cycle_time_avg_minutes != null ? `${retro.data.cycle_time_avg_minutes.toFixed(1)}m` : '—'} />
            <Row k="emergencies" v={String(retro.data.emergency_count)} />
          </dl>
        )}
      </Card>
      <Card title="Throughput by swimlane (7d)" loading={retro.isLoading} error={retro.error}>
        {retro.data && (
          <ul className="space-y-1">
            {Object.entries(retro.data.swimlane_throughput).map(([sl, n]) => (
              <li key={sl} className="flex justify-between">
                <span className="font-mono">{sl}</span>
                <span>{n}</span>
              </li>
            ))}
            {Object.keys(retro.data.swimlane_throughput).length === 0 && (
              <li className="text-[var(--cos-muted)]">no data</li>
            )}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Card({
  title,
  loading,
  error,
  children,
}: {
  title: string;
  loading: boolean;
  error: Error | null;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] p-3 text-xs">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--cos-muted)]">{title}</h3>
      {loading && <p className="text-[var(--cos-muted)]">loading…</p>}
      {error && <p className="text-[var(--cos-err)]">{error.message}</p>}
      {!loading && !error && children}
    </section>
  );
}

function TaskList({ rows }: { rows: DailyTaskRow[] }) {
  if (rows.length === 0) return <p className="text-[var(--cos-muted)]">none</p>;
  return (
    <ul className="space-y-1">
      {rows.map((r, i) => (
        <li key={`${r.task_id ?? i}`} className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-[var(--cos-muted)]">{r.task_id ?? '?'}</span>
          <span className="flex-1 truncate">{r.title ?? '—'}</span>
        </li>
      ))}
    </ul>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-[var(--cos-muted)]">{k}</dt>
      <dd className="font-mono">{v}</dd>
    </div>
  );
}
