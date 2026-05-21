import { useEffect, useMemo, useRef, useState } from 'react';
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
            dotColor={health.data ? doctorDotClass(health.data.status) : 'bg-zinc-400'}
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
function BackendTab() {
  const doctor = useApiGet<GraphDoctorPayload>(['api-graph-doctor'], '/api/graph/doctor', undefined, {
    refetchIntervalMs: 10000,
  });
  if (doctor.isLoading) return <p className="text-xs text-[var(--cos-muted)]">probing graph backend…</p>;
  if (doctor.error) return <p className="text-xs text-rose-400">{doctor.error.message}</p>;
  const data = (doctor.data?.data ?? doctor.data ?? {}) as Record<string, unknown>;
  if (!data || Object.keys(data).length === 0) {
    return <p className="text-xs text-[var(--cos-muted)]">graph_os backend reported no data.</p>;
  }
  const flat = Object.entries(data).filter(([, v]) => typeof v !== 'object' || v === null);
  const nested = Object.entries(data).filter(([, v]) => typeof v === 'object' && v !== null);
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <Section title="Backend report" cols="md:col-span-2">
        <table className="w-full text-[11px]">
          <tbody>
            {flat.map(([k, v]) => (
              <tr key={k} className="border-b border-[var(--cos-border)]">
                <td className="py-1 pr-2 text-[var(--cos-muted)]">{k}</td>
                <td className="py-1 pr-2 font-mono text-[var(--cos-text)]">{String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      {nested.map(([k, v]) => (
        <Section key={k} title={k}>
          <pre dir="ltr" className="cos-scroll max-h-64 overflow-auto rounded bg-[var(--cos-bg)] p-2 text-[10px] leading-tight">
            {JSON.stringify(v, null, 2)}
          </pre>
        </Section>
      ))}
    </div>
  );
}

// ----- sqlite (per-project DB row counts) ---------------------------
function SqliteTab() {
  const db = useApiGet<DbHealthPayload>(['api-health-db'], '/api/health/db', undefined, {
    refetchIntervalMs: 10000,
  });
  if (db.isLoading) return <p className="text-xs text-[var(--cos-muted)]">reading sqlite…</p>;
  if (db.error) return <p className="text-xs text-rose-400">{db.error.message}</p>;
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
                  ? <span className="text-rose-400">{(v as { error: string }).error}</span>
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
        {db.data.error && <p className="mt-1 text-[10px] text-rose-400">{db.data.error}</p>}
      </Section>
    </div>
  );
}

function doctorDotClass(status: string): string {
  switch (status) {
    case 'ok': return 'bg-emerald-400';
    case 'degraded': return 'bg-amber-400';
    case 'error': return 'bg-rose-400';
    default: return 'bg-zinc-400';
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
  if (error) return <p className="text-xs text-rose-400">{error.message}</p>;
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
  const stopRef = useRef(false);

  useEffect(() => {
    stopRef.current = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      try {
        const r = await fetch('/metrics', { cache: 'no-cache' });
        const text = await r.text();
        const samples = parsePrometheus(text);
        const total = samples
          .filter((s) => s.name === 'cos_web_requests_total')
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
      .map((s) => ({ label: s.labels.route ?? 'unknown', value: s.value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
    return rows;
  }, [byName]);

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
    for (const [route, m] of Object.entries(byRoute)) rows.push({ route, ...m });
    rows.sort((a, b) => b.p95 - a.p95);
    return rows.slice(0, 10);
  }, [byName]);

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
      <header className="flex items-center gap-3 text-[10px] text-[var(--cos-muted)]">
        <span>polling /metrics every 2s · buffer = last {MAX_SAMPLES * 2}s</span>
        {state.err && <span className="text-rose-400">{state.err}</span>}
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
            <a className="text-[var(--cos-accent)] hover:underline" href="/api/metrics" target="_blank" rel="noreferrer">
              /api/metrics (Prometheus text)
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/metrics" target="_blank" rel="noreferrer">
              /metrics (raw)
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
  title: string;
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
      <span className={danger ? 'font-mono text-rose-400 glow-rose font-semibold' : 'font-mono text-[var(--cos-text)] font-semibold'}>{v}</span>
    </div>
  );
}
