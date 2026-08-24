import { Section } from './DoctorPrimitives';
import { MAX_SAMPLES, SELF_POLL_ROUTES, fmtMs } from './doctor-shared';
import { resolveApiUrl } from '@/lib/api-client';
import { BarList, Gauge, Sparkline, StatTile } from '@/lib/charts';
import { indexByName, parsePrometheus } from '@/lib/prometheus-parse';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { MetricsState } from './doctor-types';

export function HealthTab() {
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
          <span>include the Hub UI&apos;s own background polling</span>
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
