import { useState } from 'react';
import { apiGet } from '@/lib/api-client';

// Producer shapes verified live against the emit site (api-contract):
// /api/graph/diff ← cos_graph_diff → cos_graph_detect_changes (graph.py:1642).
// `meta.walk_truncated` arrives in the envelope meta (unwrap pops data.meta
// to the top level), so it is the SECOND tuple element from apiGet.
interface AffectedSymbol {
  file: string;
  source: string;
  target: string;
  edge_type: string;
}
interface DownstreamConsumer {
  file: string;
  consumer: string;
  target: string;
  edge_type: string;
  confidence: number;
}
interface DiffPayload {
  scope: string;
  files: string[];
  symbols: AffectedSymbol[];
  downstream_consumers: DownstreamConsumer[];
  downstream_tasks: string[];
  risk_level: string;
}

const RISK_TONE: Record<string, string> = {
  high: 'var(--cos-err)',
  medium: 'var(--cos-warn)',
  low: 'var(--cos-accent)',
  none: 'var(--cos-muted)',
};

function uidTail(uid: string): string {
  return uid.split('/').pop() ?? uid;
}

function Group({
  title,
  count,
  empty,
  children,
}: {
  title: string;
  count: number;
  empty: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-3">
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        {title} · {count}
      </h4>
      <ul className="space-y-0.5 font-mono">
        {count === 0 ? <li className="text-[var(--cos-faint)]">{empty}</li> : children}
      </ul>
    </section>
  );
}

/**
 * Graph-aware diff triage. Enter a base..head range; the view
 * consumes /api/graph/diff (no new kernel) and shows changed symbols,
 * downstream consumers/tasks, and a coarse heuristic risk level. Works on
 * manual range entry today; a PR-ingestion feed can drive it later.
 */
export default function DiffTriagePanel() {
  const [base, setBase] = useState('HEAD~1');
  const [head, setHead] = useState('HEAD');
  const [data, setData] = useState<DiffPayload | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDiff = async () => {
    if (!base.trim() || !head.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const [payload, meta] = await apiGet<DiffPayload>('/api/graph/diff', {
        base: base.trim(),
        head: head.trim(),
      });
      setData(payload);
      setTruncated(Boolean(meta?.walk_truncated));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'diff failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="text-xs">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void fetchDiff();
        }}
        className="mb-3 flex items-center gap-2"
      >
        <input
          value={base}
          onChange={(e) => setBase(e.target.value)}
          aria-label="Base ref"
          placeholder="base"
          className="w-24 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
        />
        <span className="text-[var(--cos-faint)]">..</span>
        <input
          value={head}
          onChange={(e) => setHead(e.target.value)}
          aria-label="Head ref"
          placeholder="head"
          className="w-24 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
        />
        <button
          type="submit"
          disabled={!base.trim() || !head.trim() || loading}
          className="rounded border border-[var(--cos-accent)] px-2 py-1 font-mono text-xs text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'analyzing…' : 'triage diff'}
        </button>
      </form>
      {error && (
        <p role="alert" className="mb-2 text-[var(--cos-err)]">
          {error}
        </p>
      )}
      {data && (
        <>
          <p className="mb-2 text-[var(--cos-muted)]">
            risk:{' '}
            <span style={{ color: RISK_TONE[data.risk_level] ?? 'var(--cos-text)' }}>
              {data.risk_level}
            </span>
            <span className="ml-1 text-[var(--cos-faint)]">(heuristic — edge-count thresholds)</span>
            {' · '}
            {data.files.length} file(s)
          </p>
          {truncated && (
            <p role="status" className="mb-2 text-[var(--cos-warn)]">
              impact walk hit its visit cap — results are incomplete; narrow the range.
            </p>
          )}
          <Group title="changed symbols" count={data.symbols.length} empty="no symbol-level changes">
            {data.symbols.map((s, i) => (
              <li key={`${s.source}:${i}`} className="truncate" title={`${s.source} → ${s.target}`}>
                {s.file} · {uidTail(s.source)}
              </li>
            ))}
          </Group>
          <Group
            title="downstream consumers"
            count={data.downstream_consumers.length}
            empty="none"
          >
            {data.downstream_consumers.map((c, i) => (
              <li key={`${c.consumer}:${i}`} className="truncate" title={`${c.consumer} (${c.edge_type})`}>
                {uidTail(c.consumer)}
              </li>
            ))}
          </Group>
          <Group title="downstream tasks" count={data.downstream_tasks.length} empty="none">
            {data.downstream_tasks.map((t) => (
              <li key={t} className="truncate" title={t}>
                {uidTail(t)}
              </li>
            ))}
          </Group>
        </>
      )}
    </div>
  );
}
