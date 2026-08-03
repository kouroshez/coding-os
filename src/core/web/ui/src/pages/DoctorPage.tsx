import { useEffect, useMemo, useRef, useState } from 'react';
import { resolveApiUrl } from '@/lib/api-client';
import { useApiGet } from '@/lib/hooks';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';
import { BarList, Gauge, Sparkline, StatTile } from '@/lib/charts';
import { indexByName, parsePrometheus, type MetricSample } from '@/lib/prometheus-parse';

type Tab = 'overview' | 'health' | 'maintenance' | 'backend' | 'sqlite';

interface HealthPayload {
  status: 'ok' | 'degraded' | string;
  backend_id: string;
  edge_sample?: number;
  node_count_sample?: number;
  edge_count_sample?: number;
  file_index_state_rows?: number | null;
  file_index_state_last_indexed_at?: number | null;
  file_index_state_error?: string;
  reason?: string;
}

interface DbHealthPayload {
  db_path: string;
  exists: boolean;
  size_bytes: number;
  tables: Record<string, number | null | { error: string }>;
  diagnostics?: string[];
  error?: string;
}

interface GraphDoctorPayload {
  ok?: boolean;
  data?: Record<string, unknown>;
  [k: string]: unknown;
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'health', label: 'Health & charts' },
  { id: 'maintenance', label: 'Maintenance' },
  { id: 'backend', label: 'Backend' },
  { id: 'sqlite', label: 'sqlite' },
];

const MAX_SAMPLES = 60; // 2 minutes at 2s/poll

// Routes the SPA hits on its own timers (presence beacons, hook feeds, the
// Doctor page's own health/metrics polling). Excluded from the charts by
// default so an idle hub reads as idle — the counters otherwise climb from
// the dashboard measuring itself.
const SELF_POLL_ROUTES = new Set([
  'presence.agents',
  'presence.now',
  'hooks.recent',
  'hooks.stream',
  'sessions.active',
  'logs.summary',
  'board.list',
  'cognition.chats',
  'cognition.traces',
  'graph.doctor',
  'health',
  'health.db',
  'metrics',
]);

function fmtAge(epoch: number | null | undefined): string {
  if (!epoch) return '—';
  const diff = Math.max(0, Math.floor(Date.now() / 1000) - epoch);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function fmtMs(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  if (seconds < 0.001) return `${(seconds * 1_000_000).toFixed(0)}µs`;
  if (seconds < 1) return `${(seconds * 1000).toFixed(1)}ms`;
  return `${seconds.toFixed(2)}s`;
}


export default function DoctorPage() {
  const [tab, setTab] = useState<Tab>('overview');
  // Project-scoped via api-client rewrite — on /p/<slug>/doctor this
  // becomes /api/p/<slug>/health and the middleware swaps the DB.
  const health = useApiGet<HealthPayload>(['api-health'], '/api/health', undefined, {
    refetchIntervalMs: 5000,
  });
  return (
    <PageShell>
      <PageHeader
        eyebrow={
          <StatusPill
            label={`doctor · ${health.data?.status ?? 'probing…'}`}
            dotColor={health.data ? doctorDotClass(health.data.status) : 'bg-[var(--cos-panel)]'}
          />
        }
        title="Doctor"
        subtitle="Health probe, dependency checks, and maintenance runners. Auto-refreshes every 5 s."
      />
      <nav
        className="mb-5 flex flex-wrap gap-2 rounded-full border border-[var(--cos-border)] bg-[var(--cos-panel)]/70 p-1 backdrop-blur"
        aria-label="Doctor tabs"
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
      <div className="p-1">
        {tab === 'overview' && <OverviewTab health={health.data} loading={health.isLoading} error={health.error} />}
        {tab === 'health' && <HealthTab />}
        {tab === 'maintenance' && <MaintenanceTab health={health.data} />}
        {tab === 'backend' && <BackendTab />}
        {tab === 'sqlite' && <SqliteTab />}
      </div>
    </PageShell>
  );
}

// ----- Backend (graph) ----------------------------------------------
// Render `cos_graph_doctor` output as structured cards instead
// of a raw JSON dump. The top grid surfaces flat stats (healthy,
// node/edge counts), and each issue category from `issues[]` becomes
// its own card with a count badge + sortable sample table.
interface GraphIssue {
  category: string;
  count: number;
  sample?: Array<Record<string, unknown>>;
}
interface GraphStats {
  node_count?: number;
  edge_count?: number;
  orphaned_nodes?: number;
  // W7.6: split orphan stats — orphaned_inrepo are real bugs;
  // orphaned_external_unresolved are stdlib/3rd-party stub surface.
  orphaned_inrepo?: number;
  orphaned_external_unresolved?: number;
  issue_count?: number;
  fixed_edge_count?: number;
}
interface GraphDoctorData {
  healthy?: boolean;
  issues?: GraphIssue[];
  stats?: GraphStats;
  meta?: Record<string, unknown>;
}
const ISSUE_LABELS: Record<string, string> = {
  dangling_source: 'Dangling source edges',
  dangling_target: 'Dangling target edges',
  // W7.6: legacy `orphaned_nodes` split into in-repo (real bugs) vs
  // external-unresolved (informational stdlib stubs).
  orphaned_nodes: 'Orphaned nodes (legacy)',
  orphaned_inrepo: 'Orphaned in-repo nodes',
  orphaned_external_unresolved: 'Unresolved external stubs (info)',
  malformed_uid_path: 'Malformed UID paths',
  self_loops: 'Self-loops',
  duplicate_edges: 'Duplicate edges',
  stale_paths: 'Stale paths',
};
const ISSUE_SEVERITY: Record<string, 'real' | 'info'> = {
  orphaned_external_unresolved: 'info',
};
function BackendTab() {
  const doctor = useApiGet<GraphDoctorPayload>(['api-graph-doctor'], '/api/graph/doctor', undefined, {
    refetchIntervalMs: 10000,
  });
  if (doctor.isLoading) return <p className="text-xs text-[var(--cos-muted)]">probing graph backend…</p>;
  if (doctor.error) return <p className="text-xs text-[var(--cos-err)]">{doctor.error.message}</p>;
  const payload = (doctor.data?.data ?? doctor.data ?? {}) as GraphDoctorData;
  if (!payload || Object.keys(payload).length === 0) {
    return <p className="text-xs text-[var(--cos-muted)]">graph_os backend reported no data.</p>;
  }
  const issues = payload.issues ?? [];
  const stats = payload.stats ?? {};
  const healthy = payload.healthy ?? false;
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
      <StatTile
        label="Health"
        value={healthy ? 'OK' : 'attention'}
        tone={healthy ? 'ok' : 'warn'}
      />
      <StatTile label="Nodes" value={stats.node_count ?? '—'} tone="neutral" />
      <StatTile label="Edges" value={stats.edge_count ?? '—'} tone="neutral" />
      <StatTile
        label="Issues"
        value={stats.issue_count ?? issues.length}
        tone={(stats.issue_count ?? issues.length) > 0 ? 'warn' : 'ok'}
      />
      {issues.length === 0 ? (
        <Section title="No issues" cols="md:col-span-4">
          <p className="text-[11px] text-[var(--cos-muted)]">All graph_os health checks pass.</p>
        </Section>
      ) : (
        issues.map((issue) => <IssueCard key={issue.category} issue={issue} />)
      )}
    </div>
  );
}

function IssueCard({ issue }: { issue: GraphIssue }) {
  const label = ISSUE_LABELS[issue.category] ?? issue.category;
  const sample = issue.sample ?? [];
  // Derive columns from the first sample row; sort by string key so the
  // table layout is stable across renders. Missing keys render `—`.
  const columns = sample.length > 0 ? Object.keys(sample[0]).sort() : [];
  // W7.6: informational issues (e.g. stdlib stub orphans) use a muted
  // amber badge instead of the alarming rose so the user can tell at a
  // glance which categories require action.
  const severity = ISSUE_SEVERITY[issue.category] ?? 'real';
  const badgeClass =
    severity === 'info'
      ? 'rounded bg-[var(--cos-warn-tint)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--cos-warn)]'
      : 'rounded bg-[var(--cos-err-tint)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--cos-err)]';
  return (
    <Section
      title={
        <span className="flex items-center gap-2">
          <span>{label}</span>
          <span className={badgeClass}>
            {issue.count.toLocaleString()}
          </span>
          {severity === 'info' && (
            <span className="text-[10px] text-[var(--cos-muted)]">informational</span>
          )}
        </span>
      }
      cols="md:col-span-2"
    >
      {sample.length === 0 ? (
        <p className="text-[11px] text-[var(--cos-muted)]">no sample available.</p>
      ) : (
        <div className="cos-scroll max-h-64 overflow-auto">
          <table dir="ltr" className="w-full text-[10px]">
            <thead className="text-left text-[var(--cos-muted)]">
              <tr>
                {columns.map((c) => (
                  <th key={c} className="py-1 pr-2 font-normal">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sample.map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => {
                    const v = row[c];
                    const display =
                      v == null
                        ? <span className="text-[var(--cos-faint)]">—</span>
                        : <span className="break-all font-mono">{String(v)}</span>;
                    return (
                      <td
                        key={c}
                        className="border-t border-[var(--cos-border)] py-1 pr-2 align-top"
                      >
                        {display}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

// ----- sqlite (per-project DB row counts) ---------------------------
function SqliteTab() {
  const db = useApiGet<DbHealthPayload>(['api-health-db'], '/api/health/db', undefined, {
    refetchIntervalMs: 10000,
  });
  if (db.isLoading) return <p className="text-xs text-[var(--cos-muted)]">reading sqlite…</p>;
  if (db.error) return <p className="text-xs text-[var(--cos-err)]">{db.error.message}</p>;
  if (!db.data) return null;
  const tables = Object.entries(db.data.tables ?? {});
  const presentTables = tables.filter(([, v]) => typeof v === 'number');
  const totalRows = presentTables.reduce((acc, [, v]) => acc + (v as number), 0);
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile label="DB present" value={db.data.exists ? 'yes' : 'no'} tone={db.data.exists ? 'ok' : 'danger'} />
      <StatTile label="Size" value={db.data.exists ? `${(db.data.size_bytes / 1024).toFixed(1)} kB` : '—'} tone="neutral" />
      <StatTile label="Tables present" value={presentTables.length} tone={presentTables.length > 0 ? 'ok' : 'warn'} />
      <StatTile label="Total rows" value={totalRows} tone="neutral" />
      {(db.data.diagnostics?.length ?? 0) > 0 && (
        <Section title="⚠️ Diagnostics — why a loop may be dead" cols="md:col-span-4">
          <ul className="space-y-1.5 text-[11px] text-[var(--cos-warn)]">
            {db.data.diagnostics!.map((d, i) => (
              <li key={i} className="flex gap-2">
                <span aria-hidden>•</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="Rows by table" cols="md:col-span-4">
        {tables.length === 0 ? (
          <p className="text-[11px] text-[var(--cos-muted)]">no tables reported.</p>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-left text-[var(--cos-muted)]">
              <tr>
                <th className="py-1 pr-2">table</th>
                <th className="py-1 pr-2 text-right">rows</th>
              </tr>
            </thead>
            <tbody>
              {tables.map(([t, v]) => {
                const isError = typeof v === 'object' && v !== null && 'error' in v;
                const missing = v == null;
                const display = missing
                  ? <span className="text-[var(--cos-faint)]">absent</span>
                  : isError
                  ? <span className="text-[var(--cos-err)]">{(v as { error: string }).error}</span>
                  : <span className="font-mono">{String(v)}</span>;
                return (
                  <tr key={t}>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 font-mono">{t}</td>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 text-right">{display}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Section>
      <Section title="DB path" cols="md:col-span-4">
        <p dir="ltr" className="break-all font-mono text-[10px] text-[var(--cos-muted)]">{db.data.db_path}</p>
        {db.data.error && <p className="mt-1 text-[10px] text-[var(--cos-err)]">{db.data.error}</p>}
      </Section>
    </div>
  );
}

function doctorDotClass(status: string): string {
  switch (status) {
    case 'ok': return 'bg-[var(--cos-ok-tint)]';
    case 'degraded': return 'bg-[var(--cos-warn-tint)]';
    case 'error': return 'bg-[var(--cos-err-tint)]';
    default: return 'bg-[var(--cos-panel)]';
  }
}

// ----- Overview ------------------------------------------------------
function OverviewTab({
  health,
  loading,
  error,
}: {
  health: HealthPayload | undefined;
  loading: boolean;
  error: Error | null;
}) {
  if (loading) return <p className="text-xs text-[var(--cos-muted)]">probing…</p>;
  if (error) return <p className="text-xs text-[var(--cos-err)]">{error.message}</p>;
  if (!health) return null;

  const indexFreshness = health.file_index_state_last_indexed_at ?? null;
  const isOk = health.status === 'ok';
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile
        label="Backend"
        value={health.backend_id}
        tone={isOk ? 'ok' : 'danger'}
      />
      <StatTile label="Nodes (sample)" value={health.node_count_sample ?? '—'} tone="neutral" />
      <StatTile label="Edges (sample)" value={health.edge_count_sample ?? '—'} tone="neutral" />
      <StatTile
        label="Index rows"
        value={health.file_index_state_rows ?? '—'}
        tone={(health.file_index_state_rows ?? 0) > 0 ? 'ok' : 'warn'}
      />
      <Section title="Index freshness" cols="md:col-span-2">
        <Row k="last indexed" v={fmtAge(indexFreshness)} />
        <Row k="rows" v={String(health.file_index_state_rows ?? 0)} />
        {health.file_index_state_error && (
          <Row k="error" v={health.file_index_state_error} danger />
        )}
      </Section>
      <Section title="Probe sample" cols="md:col-span-2">
        <Row k="edge sample" v={String(health.edge_sample ?? '—')} />
        <Row k="node count sample" v={String(health.node_count_sample ?? '—')} />
        <Row k="edge count sample" v={String(health.edge_count_sample ?? '—')} />
        {health.reason && <Row k="reason" v={health.reason} danger />}
      </Section>
    </div>
  );
}

// ----- Health (charts) ----------------------------------------------
interface MetricsState {
  samples: MetricSample[];
  totalsHistory: number[]; // rolling total requests
  errorsHistory: number[]; // rolling 4xx+5xx counter (if available)
  lastTotal: number | null;
  lastFetched: number;
  err: string | null;
}

function HealthTab() {
  const [state, setState] = useState<MetricsState>({
    samples: [],
    totalsHistory: [],
    errorsHistory: [],
    lastTotal: null,
    lastFetched: 0,
    err: null,
  });
  const [includeSelfPolling, setIncludeSelfPolling] = useState(false);
  const includeSelfPollingRef = useRef(includeSelfPolling);
  includeSelfPollingRef.current = includeSelfPolling;
  const stopRef = useRef(false);

  // Flipping the filter changes the totals' scale — reset the sparkline so it
  // never mixes filtered and unfiltered points.
  useEffect(() => {
    setState((prev) => ({ ...prev, totalsHistory: [], lastTotal: null }));
  }, [includeSelfPolling]);

  useEffect(() => {
    stopRef.current = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      try {
        // /metrics is the process-wide Prometheus endpoint (global by design —
        // one uvicorn serves every project); resolveApiUrl keeps the dev base-URL
        // honored without project-scoping it. It is text/plain, so stays a raw fetch.
        const r = await fetch(resolveApiUrl('/metrics'), { cache: 'no-cache' });
        const text = await r.text();
        const samples = parsePrometheus(text);
        const total = samples
          .filter(
            (s) =>
              s.name === 'cos_web_requests_total' &&
              (includeSelfPollingRef.current || !SELF_POLL_ROUTES.has(s.labels.route ?? '')),
          )
          .reduce((acc, s) => acc + s.value, 0);
        setState((prev) => ({
          samples,
          totalsHistory: [...prev.totalsHistory, total].slice(-MAX_SAMPLES),
          errorsHistory: prev.errorsHistory, // placeholder — fill if backend exposes errors
          lastTotal: total,
          lastFetched: Date.now(),
          err: null,
        }));
      } catch (exc) {
        setState((prev) => ({ ...prev, err: (exc as Error).message }));
      } finally {
        if (!stopRef.current) timer = setTimeout(poll, 2000);
      }
    };
    void poll();
    return () => {
      stopRef.current = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const byName = useMemo(() => indexByName(state.samples), [state.samples]);

  // Top routes by request count.
  const topRoutes = useMemo(() => {
    const rows = (byName.get('cos_web_requests_total') ?? [])
      .filter((s) => includeSelfPolling || !SELF_POLL_ROUTES.has(s.labels.route ?? ''))
      .map((s) => ({ label: s.labels.route ?? 'unknown', value: s.value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
    return rows;
  }, [byName, includeSelfPolling]);

  // Latency p95 per route.
  const latencyRows = useMemo(() => {
    const rows: { route: string; count: number; avg: number; p50: number; p95: number; p99: number }[] = [];
    const counts = byName.get('cos_web_request_duration_seconds_count') ?? [];
    const avgs = byName.get('cos_web_request_duration_seconds_avg') ?? [];
    const quantSamples = byName.get('cos_web_request_duration_seconds') ?? [];
    const byRoute: Record<string, { count: number; avg: number; p50: number; p95: number; p99: number }> = {};
    for (const c of counts) {
      const r = c.labels.route ?? 'unknown';
      byRoute[r] = byRoute[r] ?? { count: 0, avg: 0, p50: 0, p95: 0, p99: 0 };
      byRoute[r].count = c.value;
    }
    for (const a of avgs) {
      const r = a.labels.route ?? 'unknown';
      byRoute[r] = byRoute[r] ?? { count: 0, avg: 0, p50: 0, p95: 0, p99: 0 };
      byRoute[r].avg = a.value;
    }
    for (const q of quantSamples) {
      const r = q.labels.route ?? 'unknown';
      const which = q.labels.quantile;
      if (!which || !byRoute[r]) continue;
      if (which === '0.5') byRoute[r].p50 = q.value;
      else if (which === '0.95') byRoute[r].p95 = q.value;
      else if (which === '0.99') byRoute[r].p99 = q.value;
    }
    for (const [route, m] of Object.entries(byRoute)) {
      if (!includeSelfPolling && SELF_POLL_ROUTES.has(route)) continue;
      rows.push({ route, ...m });
    }
    rows.sort((a, b) => b.p95 - a.p95);
    return rows.slice(0, 10);
  }, [byName, includeSelfPolling]);

  const totalRequests = state.lastTotal ?? 0;
  const reqRate = (() => {
    const n = state.totalsHistory.length;
    if (n < 2) return 0;
    const delta = state.totalsHistory[n - 1] - state.totalsHistory[Math.max(0, n - 6)];
    const sec = Math.max(1, (Math.min(n, 6) - 1) * 2); // 2s/poll
    return delta / sec;
  })();
  const slowRoutes = latencyRows.filter((r) => r.p95 > 0.5).length;

  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-center gap-3 text-[10px] text-[var(--cos-muted)]">
        <span>polling /metrics every 2s · buffer = last {MAX_SAMPLES * 2}s</span>
        <span>·</span>
        <span>Prometheus counters from FastAPI middleware (cos_web_requests_total)</span>
        <label className="flex cursor-pointer items-center gap-1.5">
          <input
            type="checkbox"
            checked={includeSelfPolling}
            onChange={(e) => setIncludeSelfPolling(e.target.checked)}
            className="h-3 w-3 accent-[var(--cos-accent)]"
          />
          <span>include the Hub UI's own background polling</span>
        </label>
        {state.err && <span className="text-[var(--cos-err)]">{state.err}</span>}
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Total requests" value={totalRequests} spark={state.totalsHistory} tone="ok" />
        <StatTile label="Rate (req/s)" value={reqRate.toFixed(2)} tone={reqRate > 5 ? 'warn' : 'neutral'} />
        <StatTile
          label="Slow routes (p95>500ms)"
          value={slowRoutes}
          tone={slowRoutes === 0 ? 'ok' : slowRoutes < 3 ? 'warn' : 'danger'}
        />
        <StatTile label="Routes tracked" value={topRoutes.length} tone="neutral" />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Section title="Top routes (total requests)">
          <BarList
            rows={topRoutes}
            formatValue={(v) => String(v)}
            emptyText="no traffic recorded yet — try poking the UI."
          />
        </Section>
        <Section title="Latency p95 (top 10)">
          {latencyRows.length === 0 ? (
            <p className="text-xs text-[var(--cos-muted)]">no latency data yet.</p>
          ) : (
            <table className="w-full text-[11px]">
              <thead className="text-left text-[var(--cos-muted)]">
                <tr>
                  <th className="py-1 pr-2">route</th>
                  <th className="py-1 pr-2 text-right">count</th>
                  <th className="py-1 pr-2 text-right">avg</th>
                  <th className="py-1 pr-2 text-right">p50</th>
                  <th className="py-1 pr-2 text-right">p95</th>
                  <th className="py-1 pr-2 text-right">p99</th>
                </tr>
              </thead>
              <tbody>
                {latencyRows.map((r) => (
                  <tr key={r.route} className="hover:bg-[var(--cos-grain)]">
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 font-mono">{r.route}</td>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 text-right">{r.count}</td>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 text-right">{fmtMs(r.avg)}</td>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 text-right">{fmtMs(r.p50)}</td>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 text-right">{fmtMs(r.p95)}</td>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 text-right">{fmtMs(r.p99)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Section title="Slowest route (p95)">
          {latencyRows[0] ? (
            <div className="space-y-2">
              <div className="font-mono text-xs">{latencyRows[0].route}</div>
              <Gauge
                value={Math.min(1000, Math.round(latencyRows[0].p95 * 1000))}
                max={1000}
                label="p95 (ms)"
                warnFrom={0.5}
                dangerFrom={0.9}
              />
            </div>
          ) : (
            <p className="text-xs text-[var(--cos-muted)]">no traffic.</p>
          )}
        </Section>
        <Section title="Request throughput">
          <Sparkline data={state.totalsHistory} width={260} height={64} label="cumulative requests" />
          <p className="mt-1 text-[10px] text-[var(--cos-muted)]">
            cumulative request counter — slope = req/s
          </p>
        </Section>
        <Section title="Hottest endpoint">
          {topRoutes[0] ? (
            <div className="space-y-1">
              <div className="font-mono text-xs">{topRoutes[0].label}</div>
              <div className="text-xl font-bold text-[var(--cos-accent)]">{topRoutes[0].value}</div>
              <p className="text-[10px] text-[var(--cos-muted)]">total requests since hub start.</p>
            </div>
          ) : (
            <p className="text-xs text-[var(--cos-muted)]">no data.</p>
          )}
        </Section>
      </div>
    </div>
  );
}

// ----- Maintenance ---------------------------------------------------
function MaintenanceTab({ health }: { health: HealthPayload | undefined }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <Section title="Repair commands">
        <ul className="space-y-2 text-[11px]">
          <li>
            <span className="text-[var(--cos-muted)]">backend degraded → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos graph-reindex --force</code>
          </li>
          <li>
            <span className="text-[var(--cos-muted)]">stale index → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos graph-reindex</code>
          </li>
          <li>
            <span className="text-[var(--cos-muted)]">full system check → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos doctor</code>
          </li>
          <li>
            <span className="text-[var(--cos-muted)]">restart hub → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos hub stop && cos hub start</code>
          </li>
          <li>
            <span className="text-[var(--cos-muted)]">tail hub log → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos hub logs</code>
          </li>
        </ul>
      </Section>
      <Section title="Quick links">
        <ul className="space-y-1 text-[11px]">
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/metrics" target="_blank" rel="noreferrer">
              /metrics (Prometheus text)
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/docs" target="_blank" rel="noreferrer">
              /docs (OpenAPI Swagger)
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/openapi.json" target="_blank" rel="noreferrer">
              /openapi.json
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/health" target="_blank" rel="noreferrer">
              /health (raw JSON)
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/redoc" target="_blank" rel="noreferrer">
              /redoc (alt API docs)
            </a>
          </li>
        </ul>
      </Section>
      <Section title="Reported by /health" cols="md:col-span-2">
        {health ? (
          <pre className="cos-scroll max-h-64 overflow-auto rounded bg-[var(--cos-grain,#f4efe1)]/40 p-2 text-[10px] leading-tight">
            {JSON.stringify(health, null, 2)}
          </pre>
        ) : (
          <p className="text-xs text-[var(--cos-muted)]">no health payload.</p>
        )}
      </Section>
    </div>
  );
}

// ----- shared atoms --------------------------------------------------
function Section({
  title,
  cols,
  children,
}: {
  title: React.ReactNode;
  cols?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={['glass-card rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/50 p-5 text-xs transition-all duration-200 hover:-translate-y-0.5 shadow-sm', cols ?? ''].join(' ')}>
      <h3 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-[var(--accent)]">{title}</h3>
      {children}
    </section>
  );
}

function Row({ k, v, danger }: { k: string; v: string; danger?: boolean }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-[var(--cos-border)] last:border-b-0 text-[11px]">
      <span className="text-[var(--cos-muted)] font-medium">{k}</span>
      <span className={danger ? 'font-mono text-[var(--cos-err)] glow-rose font-semibold' : 'font-mono text-[var(--cos-text)] font-semibold'}>{v}</span>
    </div>
  );
}
