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

export default function MemoryPage() {
  const { slug } = useParams<{ slug?: string }>();
  const [patterns, setPatterns] = useState<PatternRow[]>([]);
  const [filter, setFilter] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');

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
  }, [slug, filter]);

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-3xl space-y-5">
        <header className="space-y-2">
          <div className="flex items-center justify-between gap-4">
            <h1 className="text-xl font-semibold text-[var(--cos-text)]">Agent Memory</h1>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2.5 py-1 text-sm text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
            >
              <option value="">All patterns</option>
              <option value="validated">Validated</option>
              <option value="volatile">Forming</option>
            </select>
          </div>
          <p className="text-sm text-[var(--cos-muted)]">
            Patterns the agent has learned across sessions from past task outcomes.
            Confidence reflects how strongly each is trusted; “confirmed” counts how
            many times it was re-observed.
          </p>
        </header>

        {loading && <div className="text-sm text-[var(--cos-muted)]">Loading…</div>}
        {error && (
          <div className="rounded-md border border-[var(--cos-err)] bg-[var(--cos-err-tint)] px-3 py-2 text-sm text-[var(--cos-err)]">
            Failed to load patterns: {error}
          </div>
        )}
        {!loading && !error && patterns.length === 0 && (
          <div className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-6 text-sm text-[var(--cos-muted)]">
            No learned patterns yet. They appear once the learning loop distils
            patterns from task outcomes (nightly, or every 10th task).
          </div>
        )}

        {patterns.length > 0 && (
          <div className="space-y-2.5">
            {patterns.map((p) => {
              const pct = Math.round((p.confidence ?? 0) * 100);
              const tier = tierBadge(p.trust_tier);
              return (
                <div
                  key={p.id}
                  className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-3 transition-colors hover:border-[var(--cos-border-strong)]"
                >
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
                        style={{
                          backgroundColor: 'var(--cos-brand-tint)',
                          color: 'var(--cos-brand-text)',
                        }}
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
            })}
          </div>
        )}
      </div>
    </div>
  );
}
