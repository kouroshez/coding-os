import { useMemo, useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { kindColor } from '@/lib/node-colors';

// Edge tier shape returned by /api/graph/impact/{uid} (TASK-074).
interface ImpactEdge {
  source_uid: string;
  target_uid: string;
  edge_type: string;
  confidence: number;
  extractor: string;
  source_span?: string | null;
}

interface ImpactPayload {
  root?: {
    uid: string;
    kind: string;
    label?: string;
    file_path?: string;
    start_line?: number;
  };
  direction?: 'in' | 'out' | 'both';
  tiers?: Record<string, ImpactEdge[]>;
}

const EDGE_GLYPH: Record<string, string> = {
  calls: '→',
  imports: '⇢',
  inherits_from: '▲',
  implements: '◇',
  has_param_type: '∋',
  returns_type: '↩',
  field_of_type: '·',
  references_doc: '✎',
  contains: '⊇',
};

const EDGE_FILTERS = ['calls', 'imports', 'inherits_from', 'implements'] as const;
type EdgeFilter = (typeof EDGE_FILTERS)[number];

/**
 * Inspector "Impact" tab — TASK-074.
 *
 * Renders Upstream (incoming edges) and Downstream (outgoing edges)
 * sections keyed off the focused node.  The backend already aggregates
 * tiers via `cos_graph_impact`; this component is a thin presentation
 * layer.  Edge-kind filters work client-side so toggling does not
 * trigger a refetch.
 */
export default function ImpactPanel({ uid }: { uid: string }) {
  const [filters, setFilters] = useState<Set<EdgeFilter>>(
    () => new Set(EDGE_FILTERS),
  );

  const { data, isLoading, error } = useApiGet<ImpactPayload>(
    ['graph-impact', uid],
    `/api/graph/impact/${encodeURIComponent(uid)}`,
    { direction: 'both', depth: 3 },
  );

  const { upstream, downstream } = useMemo(() => {
    const ups: ImpactEdge[] = [];
    const downs: ImpactEdge[] = [];
    const tiers = data?.tiers ?? {};
    for (const tier of Object.values(tiers)) {
      for (const e of tier ?? []) {
        if (e.target_uid === uid) ups.push(e);
        else if (e.source_uid === uid) downs.push(e);
      }
    }
    return { upstream: ups, downstream: downs };
  }, [data, uid]);

  const filterFn = (e: ImpactEdge) => {
    if (filters.size === EDGE_FILTERS.length) return true;
    return (filters as Set<string>).has(e.edge_type);
  };

  if (isLoading) {
    return (
      <div className="p-3 text-xs text-[var(--cos-muted)]" role="status">
        loading impact…
      </div>
    );
  }
  if (error) {
    return (
      <div role="alert" className="p-3 text-xs text-rose-400">
        {error.message}
      </div>
    );
  }

  const upFiltered = upstream.filter(filterFn);
  const downFiltered = downstream.filter(filterFn);

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-3 text-xs cos-scroll">
      <FilterToggles filters={filters} onChange={setFilters} />

      <ImpactSection
        title={`Upstream (who depends on me) — ${upFiltered.length}`}
        edges={upFiltered}
        peerKey="source"
        emptyMessage="no inbound dependencies — likely an entry point"
      />

      <ImpactSection
        title={`Downstream (what I depend on) — ${downFiltered.length}`}
        edges={downFiltered}
        peerKey="target"
        emptyMessage="no outbound dependencies"
      />
    </div>
  );
}

function FilterToggles({
  filters,
  onChange,
}: {
  filters: Set<EdgeFilter>;
  onChange: (next: Set<EdgeFilter>) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="mr-1 text-[var(--cos-muted)]">edges:</span>
      {EDGE_FILTERS.map((f) => {
        const active = filters.has(f);
        return (
          <button
            key={f}
            type="button"
            aria-pressed={active}
            className={[
              'rounded border px-1.5 py-0.5',
              active
                ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]'
                : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:bg-[var(--cos-panel)]',
            ].join(' ')}
            onClick={() => {
              const next = new Set(filters);
              if (active) next.delete(f);
              else next.add(f);
              onChange(next);
            }}
          >
            {EDGE_GLYPH[f] ?? '·'} {f}
          </button>
        );
      })}
    </div>
  );
}

function ImpactSection({
  title,
  edges,
  peerKey,
  emptyMessage,
}: {
  title: string;
  edges: ImpactEdge[];
  peerKey: 'source' | 'target';
  emptyMessage: string;
}) {
  const PAGE_SIZE = 50;
  const [showAll, setShowAll] = useState(false);
  const sorted = useMemo(
    () => [...edges].sort((a, b) => b.confidence - a.confidence),
    [edges],
  );
  const visible = showAll ? sorted : sorted.slice(0, PAGE_SIZE);

  return (
    <section>
      <h3 className="mb-1 font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        {title}
      </h3>
      {sorted.length === 0 ? (
        <p className="text-[var(--cos-muted)]">{emptyMessage}</p>
      ) : (
        <ul className="space-y-1">
          {visible.map((e) => {
            const peerUid = peerKey === 'source' ? e.source_uid : e.target_uid;
            const glyph = EDGE_GLYPH[e.edge_type] ?? '·';
            const conf = Math.round(e.confidence * 100);
            return (
              <li
                key={`${e.source_uid}->${e.target_uid}:${e.edge_type}`}
                className="flex items-start gap-1"
                title={peerUid}
              >
                <span className="text-[var(--cos-accent)]">{glyph}</span>
                <span className="flex-1 truncate font-mono">{labelOf(peerUid)}</span>
                <ConfidenceBar percent={conf} />
                <span className="w-8 text-right tabular-nums text-[var(--cos-muted)]">
                  {conf}%
                </span>
              </li>
            );
          })}
          {sorted.length > PAGE_SIZE && !showAll && (
            <li>
              <button
                type="button"
                className="text-[var(--cos-accent)] hover:underline"
                onClick={() => setShowAll(true)}
              >
                show all {sorted.length}
              </button>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}

function ConfidenceBar({ percent }: { percent: number }) {
  return (
    <span
      className="mt-1 inline-block h-1 w-10 rounded bg-[var(--cos-border)]"
      aria-label={`confidence ${percent}%`}
    >
      <span
        className="block h-full rounded"
        style={{
          width: `${Math.max(2, Math.min(100, percent))}%`,
          background: kindColor('function'),
        }}
      />
    </span>
  );
}

function labelOf(uid: string): string {
  const tail = uid.includes('::') ? uid.split('::').pop() ?? uid : uid;
  return tail.length > 60 ? `${tail.slice(0, 57)}…` : tail;
}
