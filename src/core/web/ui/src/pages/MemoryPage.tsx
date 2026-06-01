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

function tierClass(tier: string): string {
  if (tier === 'validated') return 'text-emerald-600';
  if (tier === 'volatile') return 'text-amber-600';
  return 'text-gray-500';
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
    <div className="p-6 space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Learned Patterns (Agent Memory)</h1>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="border rounded px-2 py-1 text-sm"
        >
          <option value="">All tiers</option>
          <option value="validated">Validated</option>
          <option value="volatile">Volatile</option>
        </select>
      </header>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}
      {error && (
        <div className="text-sm text-red-600">Failed to load patterns: {error}</div>
      )}
      {!loading && !error && patterns.length === 0 && (
        <div className="text-sm text-gray-500">
          No learned patterns yet. They appear once the learning loop extracts
          patterns from task outcomes (cos_learn_extract, nightly or every 10th
          task).
        </div>
      )}

      {patterns.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2 pr-4">Pattern</th>
              <th className="py-2 pr-4">Domain</th>
              <th className="py-2 pr-4">Confidence</th>
              <th className="py-2 pr-4">Impact</th>
              <th className="py-2 pr-4">Tier</th>
              <th className="py-2 pr-4">Validated</th>
              <th className="py-2 pr-4">Used</th>
              <th className="py-2 pr-4">Decay</th>
            </tr>
          </thead>
          <tbody>
            {patterns.map((p) => (
              <tr key={p.id} className="border-b align-top">
                <td className="py-2 pr-4 max-w-md">{p.pattern}</td>
                <td className="py-2 pr-4 text-xs">{p.domain ?? '—'}</td>
                <td className="py-2 pr-4">
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-gray-200 rounded">
                      <div
                        className="h-2 bg-blue-500 rounded"
                        style={{ width: `${Math.round(p.confidence * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-600">
                      {p.confidence.toFixed(2)}
                    </span>
                  </div>
                </td>
                <td className="py-2 pr-4 text-xs">{p.impact_score.toFixed(2)}</td>
                <td className={`py-2 pr-4 text-xs ${tierClass(p.trust_tier)}`}>
                  {p.trust_tier}
                </td>
                <td className="py-2 pr-4 text-xs">
                  {p.times_validated}
                  {p.times_violated > 0 && (
                    <span className="text-red-500"> / -{p.times_violated}</span>
                  )}
                </td>
                <td className="py-2 pr-4 text-xs">{p.access_count}</td>
                <td className="py-2 pr-4 text-xs text-gray-500">
                  {p.decay_rate.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
