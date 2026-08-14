import { useMemo, type JSX } from 'react';
import { useApiGet } from '@/lib/hooks';
import { kindColor } from '@/lib/node-colors';

// Same shape as the existing /api/graph/context payload — duplicated
// here to keep the panel self-contained.  Backend file: core/graph_os/
// tools/graph.py::cos_graph_context.
interface ContextEdge {
  source_uid: string;
  target_uid: string;
  edge_type: string;
  confidence: number;
  source_span?: string | null;
}

interface ContextPayload {
  node?: { uid: string; kind: string; label?: string; file_path?: string };
  edges_by_type?: Record<string, ContextEdge[]>;
}

const HERITAGE_EDGE_TYPES = new Set([
  'inherits_from',
  'extends',
  'implements',
]);

const HERITAGE_GLYPH: Record<string, string> = {
  inherits_from: '▲',
  extends: '▲',
  implements: '◇',
};

/**
 * Inspector "360°" tab —
 *
 * Single-shot read of `/api/graph/context` then client-side bucketing
 * into the five sections the advanced graph tooling parity matrix calls out:
 *   1. Heritage  (inherits_from / extends / implements outgoing)
 *   2. Incoming calls
 *   3. Incoming imports
 *   4. Outgoing calls
 * 5. Member of processes — empty/hidden until lands.
 *
 * No N+1 fetches: bucketing happens locally, the network is one
 * request.  When the focused node has zero callers we surface a
 * friendly "entry point?" empty state pointing at the entry-point
 * list.
 */
export default function ContextPanel({ uid }: { uid: string }) {
  const { data, isLoading, error } = useApiGet<ContextPayload>(
    ['graph-context-360', uid],
    `/api/graph/context/${encodeURIComponent(uid)}`,
    { depth: 1, include_content: false, include_evidence: false, include_spine: true },
  );

  const buckets = useMemo(() => {
    const out: {
      heritage: ContextEdge[];
      incomingCalls: ContextEdge[];
      incomingImports: ContextEdge[];
      outgoingCalls: ContextEdge[];
      processMembership: ContextEdge[];
    } = {
      heritage: [],
      incomingCalls: [],
      incomingImports: [],
      outgoingCalls: [],
      processMembership: [],
    };
    const ebt = data?.edges_by_type ?? {};
    for (const [edgeType, edges] of Object.entries(ebt)) {
      for (const e of edges ?? []) {
        const isOutgoing = e.source_uid === uid;
        const isIncoming = e.target_uid === uid;
        if (HERITAGE_EDGE_TYPES.has(edgeType) && isOutgoing) {
          out.heritage.push(e);
        } else if (edgeType === 'calls') {
          if (isIncoming) out.incomingCalls.push(e);
          else if (isOutgoing) out.outgoingCalls.push(e);
        } else if (edgeType === 'imports' && isIncoming) {
          out.incomingImports.push(e);
        } else if (edgeType === 'member_of_community') {
          out.processMembership.push(e);
        }
      }
    }
    return out;
  }, [data, uid]);

  if (isLoading) {
    return (
      <p role="status" className="p-3 text-xs text-[var(--cos-muted)]">
        loading 360°…
      </p>
    );
  }
  if (error) {
    return (
      <p role="alert" className="p-3 text-xs text-[var(--cos-err)]">
        {error.message}
      </p>
    );
  }
  if (!data?.node) {
    return (
      <p className="p-3 text-xs text-[var(--cos-muted)]">node not found.</p>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-3 text-xs cos-scroll">
      <Section title="Heritage" icon="▲" edges={buckets.heritage} peerKey="target" emptyMessage="no extends/implements relationships">
        {(e) => (
          <span>
            <span className="mr-1">{HERITAGE_GLYPH[e.edge_type] ?? '·'}</span>
            <span className="font-mono">{labelOf(e.target_uid)}</span>
          </span>
        )}
      </Section>

      <Section
        title={`Incoming calls — ${buckets.incomingCalls.length}`}
        icon="←"
        edges={buckets.incomingCalls.slice(0, 20)}
        peerKey="source"
        emptyMessage="no callers in the indexed graph — entry point? (see Hub Graph tab quick-action list)"
      />

      <Section
        title={`Incoming imports — ${buckets.incomingImports.length}`}
        icon="⇠"
        edges={buckets.incomingImports.slice(0, 20)}
        peerKey="source"
        emptyMessage="no inbound imports"
      />

      <Section
        title={`Outgoing calls — ${buckets.outgoingCalls.length}`}
        icon="→"
        edges={buckets.outgoingCalls.slice(0, 20)}
        peerKey="target"
        emptyMessage="no outbound calls"
      />

      {buckets.processMembership.length > 0 && (
        <Section
          title={`Member of processes — ${buckets.processMembership.length}`}
          icon="≡"
          edges={buckets.processMembership}
          peerKey="target"
          emptyMessage=""
        />
      )}
    </div>
  );
}

function Section({
  title,
  icon,
  edges,
  peerKey,
  emptyMessage,
  children,
}: {
  title: string;
  icon: string;
  edges: ContextEdge[];
  peerKey: 'source' | 'target';
  emptyMessage: string;
  children?: (e: ContextEdge) => JSX.Element;
}) {
  return (
    <details
      className="rounded border border-[var(--cos-border)] open:bg-[var(--cos-panel)]/40"
      open={edges.length > 0 && edges.length <= 5}
    >
      <summary className="cursor-pointer select-none px-2 py-1 font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        <span className="mr-1 text-[var(--cos-accent)]">{icon}</span>
        {title}
      </summary>
      <div className="border-t border-[var(--cos-border)] px-2 py-1">
        {edges.length === 0 ? (
          <p className="text-[var(--cos-muted)]">{emptyMessage}</p>
        ) : (
          <ul className="space-y-0.5">
            {edges.map((e) => {
              const peerUid =
                peerKey === 'source' ? e.source_uid : e.target_uid;
              return (
                <li
                  key={`${e.source_uid}->${e.target_uid}:${e.edge_type}`}
                  className="flex items-center gap-1 truncate"
                  title={peerUid}
                >
                  <span
                    className="inline-block h-2 w-2 rounded-sm"
                    style={{ background: kindColor('function') }}
                    aria-hidden
                  />
                  {children ? (
                    children(e)
                  ) : (
                    <span className="font-mono">{labelOf(peerUid)}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </details>
  );
}

function labelOf(uid: string): string {
  const tail = uid.includes('::') ? uid.split('::').pop() ?? uid : uid;
  return tail.length > 60 ? `${tail.slice(0, 57)}…` : tail;
}
