import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

// Field names mirror src/core/web/routes/patterns.py::_COLUMNS exactly
// (api-contract-discipline — the producer is the source of truth).
interface PatternRow {
  id: number;
  pattern: string;
  memory_type: string;
  domain: string | null;
  source: string | null;
  confidence: number;
  decay_rate: number;
  impact_score: number;
  times_validated: number;
  times_violated: number;
  access_count: number;
  trust_tier: string;
  provenance: string;
  promoted_to: string | null;
  last_validated: string | null;
  last_accessed_at: string | null;
  created_at: string;
}

interface PatternsEnvelope {
  ok: boolean;
  data: { patterns: PatternRow[]; count: number; total_count: number };
}

// Field names mirror src/core/web/routes/patterns.py::learning_roi exactly.
interface RoiSession {
  session_id: string;
  friction: number;
  total: number;
  rate: number;
  started: string;
}
interface RoiData {
  sessions: RoiSession[];
  count: number;
  trend: string;
  delta_pct: number;
}
interface RoiEnvelope {
  ok: boolean;
  data: RoiData;
}

function roiColor(trend: string): string {
  if (trend === 'improving') return 'var(--cos-ok)';
  if (trend === 'worsening') return 'var(--cos-err)';
  return 'var(--cos-muted)';
}
function roiLabel(trend: string): string {
  if (trend === 'improving') return '↓ improving';
  if (trend === 'worsening') return '↑ worsening';
  return '→ flat';
}

function api(slug: string | undefined, path: string): string {
  const base = slug ? `/api/p/${slug}` : '/api';
  return `${base}${path}`;
}

// Confidence drives the bar colour — meaning, not decoration. Solid status
// tokens stay legible on BOTH the light and dark Hub themes (the old .14
// tints washed out on light backgrounds).
function confColor(c: number): string {
  if (c >= 0.8) return 'var(--cos-ok)';
  if (c >= 0.5) return 'var(--cos-accent)';
  return 'var(--cos-warn)';
}

function tierBadge(tier: string): { label: string; bg: string; fg: string } {
  if (tier === 'validated')
    return { label: 'Validated', bg: 'var(--cos-ok-tint)', fg: 'var(--cos-ok)' };
  if (tier === 'volatile')
    return { label: 'Forming', bg: 'var(--cos-warn-tint)', fg: 'var(--cos-warn)' };
  return { label: tier || 'unknown', bg: 'var(--cos-overlay)', fg: 'var(--cos-muted)' };
}

// 'stat' rows are success-rate baselines (observability) — shown separately,
// never as a learning. Everything else is a belief/lesson.
function isStat(p: PatternRow): boolean {
  return p.memory_type === 'stat';
}

function PatternCard({ p }: { p: PatternRow }) {
  const pct = Math.round((p.confidence ?? 0) * 100);
  const tier = tierBadge(p.trust_tier);
  return (
    <div className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-3 transition-colors hover:border-[var(--cos-border-strong)]">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm leading-snug text-[var(--cos-text)]">{p.pattern}</p>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
          style={{ backgroundColor: tier.bg, color: tier.fg }}
        >
          {tier.label}
        </span>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-[var(--cos-muted)]">
        {p.domain && (
          <span
            className="rounded px-1.5 py-0.5 font-medium"
            style={{ backgroundColor: 'var(--cos-brand-tint)', color: 'var(--cos-brand-text)' }}
          >
            {p.domain}
          </span>
        )}
        <span className="flex items-center gap-2">
          <span
            className="h-1.5 w-28 overflow-hidden rounded-full"
            style={{ backgroundColor: 'var(--cos-overlay)' }}
          >
            <span
              className="block h-full rounded-full"
              style={{ width: `${pct}%`, backgroundColor: confColor(p.confidence ?? 0) }}
            />
          </span>
          <span className="tabular-nums text-[var(--cos-text)]">{pct}%</span>
          <span>confidence</span>
        </span>
        {p.times_validated > 0 && (
          <span className="tabular-nums">confirmed {p.times_validated}×</span>
        )}
        {p.times_violated > 0 && (
          <span className="tabular-nums text-[var(--cos-err)]">
            contradicted {p.times_violated}×
          </span>
        )}
      </div>
    </div>
  );
}

export default function MemoryPage() {
  const { slug } = useParams<{ slug?: string }>();
  const [patterns, setPatterns] = useState<PatternRow[]>([]);
  const [filter, setFilter] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [reloadCounter, setReloadCounter] = useState<number>(0);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [running, setRunning] = useState<boolean>(false);
  const [runMsg, setRunMsg] = useState<string>('');
  const [roi, setRoi] = useState<RoiData | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = filter ? `?trust_tier=${encodeURIComponent(filter)}` : '';
    fetch(api(slug, `/patterns${qs}`))
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<PatternsEnvelope>;
      })
      .then((env) => {
        if (cancelled) return;
        setPatterns(env.data?.patterns ?? []);
        setError('');
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, filter, reloadCounter]);

  // When the loop last ran (read-only) — drives the "Last run" label.
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    fetch(`/api/scheduled/project/${encodeURIComponent(slug)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && d) setLastRun((d.run_at as string) ?? null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug, reloadCounter]);

  // Learning effectiveness: friction-per-session trend (does it go down over time?).
  useEffect(() => {
    let cancelled = false;
    fetch(api(slug, '/patterns/roi'))
      .then((r) => (r.ok ? (r.json() as Promise<RoiEnvelope>) : null))
      .then((env) => {
        if (!cancelled && env?.data) setRoi(env.data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug, reloadCounter]);

  // Manual trigger — runs the same nightly loop (decay + learn-extract + digest)
  // and refetches so the freshly-distilled lessons appear immediately.
  async function runLoop(): Promise<void> {
    if (!slug || running) return;
    setRunning(true);
    setRunMsg('');
    try {
      const r = await fetch(`/api/scheduled/run/${encodeURIComponent(slug)}`, { method: 'POST' });
      const d = await r.json();
      const lx = d?.summary?.tasks?.learn_extract;
      if (d?.ran && lx?.status === 'ok') {
        const n = Array.isArray(lx.extracted) ? lx.extracted.length : 0;
        setRunMsg(
          `Done — distilled ${n} pattern${n === 1 ? '' : 's'} from ${lx.total_outcomes_analyzed ?? 0} outcomes.`,
        );
      } else if (d?.ran && lx?.status === 'skipped') {
        setRunMsg('Done — no new outcomes to learn from yet.');
      } else if (d?.ran) {
        setRunMsg('Done.');
      } else {
        setRunMsg(`Failed: ${d?.error ?? 'unknown error'}`);
      }
      setReloadCounter((c) => c + 1);
    } catch (e) {
      setRunMsg(`Failed: ${String(e)}`);
    } finally {
      setRunning(false);
    }
  }

  const lessons = patterns.filter((p) => !isStat(p));
  const stats = patterns.filter(isStat);

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <header className="space-y-2">
          <div className="flex items-center justify-between gap-4">
            <h1 className="text-xl font-semibold text-[var(--cos-text)]">Agent Memory</h1>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2.5 py-1 text-sm text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
            >
              <option value="">All</option>
              <option value="validated">Validated</option>
              <option value="volatile">Forming</option>
            </select>
          </div>
          <p className="text-sm text-[var(--cos-muted)]">
            <strong className="text-[var(--cos-text)]">Lessons</strong> are what the agent
            learned from real friction — blocked actions, tool failures, and reworks it hit
            in earlier sessions — so it avoids the same mistake next time.{' '}
            <strong className="text-[var(--cos-text)]">Project stats</strong> below are
            success rates, shown for context — not lessons.
          </p>
          {slug && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-2 text-xs text-[var(--cos-muted)]">
              <button
                type="button"
                onClick={runLoop}
                disabled={running}
                className="rounded-md px-2.5 py-1 font-medium disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
                style={{ backgroundColor: 'var(--cos-brand-tint)', color: 'var(--cos-brand-text)' }}
              >
                {running ? 'Running…' : 'Run learning loop now'}
              </button>
              <span>
                Last run:{' '}
                <span className="text-[var(--cos-text)]">
                  {lastRun ? new Date(lastRun).toLocaleString() : 'never'}
                </span>
              </span>
              {runMsg && <span className="text-[var(--cos-text)]">{runMsg}</span>}
            </div>
          )}
        </header>

        {loading && <div className="text-sm text-[var(--cos-muted)]">Loading…</div>}
        {error && (
          <div className="rounded-md border border-[var(--cos-err)] bg-[var(--cos-err-tint)] px-3 py-2 text-sm text-[var(--cos-err)]">
            Failed to load patterns: {error}
          </div>
        )}
        {!loading && !error && patterns.length === 0 && (
          <div className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-6 text-sm text-[var(--cos-muted)]">
            No lessons yet. The agent distils lessons from friction (blocked actions,
            failures, reworks) when the learning loop runs — nightly or every 10th task.
          </div>
        )}

        {roi && roi.sessions.length >= 2 && (
          <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-[var(--cos-text)]">Learning effectiveness</h2>
              <span className="text-xs font-medium" style={{ color: roiColor(roi.trend) }}>
                {roiLabel(roi.trend)}
                {roi.delta_pct ? ` ${roi.delta_pct > 0 ? '+' : ''}${roi.delta_pct}%` : ''}
              </span>
            </div>
            <p className="mt-1 text-xs text-[var(--cos-muted)]">
              Friction (blocks + errors) per session — lower is better. Last{' '}
              {roi.sessions.length} sessions.
            </p>
            <div className="mt-2 flex h-10 items-end gap-0.5">
              {roi.sessions.map((s, i) => {
                const max = Math.max(...roi.sessions.map((x) => x.rate), 0.01);
                const h = Math.max(6, Math.round((s.rate / max) * 100));
                return (
                  <span
                    key={`${s.session_id}-${i}`}
                    title={`${(s.rate * 100).toFixed(0)}% friction (${s.friction}/${s.total})`}
                    className="flex-1 rounded-sm"
                    style={{ height: `${h}%`, backgroundColor: roiColor(roi.trend) }}
                  />
                );
              })}
            </div>
          </section>
        )}

        {lessons.length > 0 && (
          <section className="space-y-2.5">
            <h2 className="text-sm font-semibold text-[var(--cos-text)]">
              Lessons learned <span className="text-[var(--cos-muted)]">({lessons.length})</span>
            </h2>
            {lessons.map((p) => (
              <PatternCard key={p.id} p={p} />
            ))}
          </section>
        )}

        {stats.length > 0 && (
          <section className="space-y-2.5">
            <h2 className="text-sm font-semibold text-[var(--cos-muted)]">
              Project stats — success rates, not lessons{' '}
              <span className="text-[var(--cos-muted)]">({stats.length})</span>
            </h2>
            {stats.map((p) => (
              <PatternCard key={p.id} p={p} />
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
