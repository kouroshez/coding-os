import { ExternalLink } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { kindColor } from '@/lib/node-colors';

interface Neighbour {
  uid: string;
  kind?: string;
  label?: string;
  edge_type?: string;
}

interface ContextPayload {
  node?: {
    uid: string;
    kind: string;
    label?: string;
    file_path?: string;
    start_line?: number;
    end_line?: number;
    signature?: string;
    doc_blob?: string;
  };
  neighbours?: Neighbour[];
  edges_by_type?: Record<string, Neighbour[]>;
  spine?: { uid: string; kind: string; label?: string }[];
}

// Right-pane node inspector. Calls /api/graph/context and renders the
// key fields plus an "Open in Editor" vscode:// link when file_path
// is known.
export default function NodeInspector({ uid }: { uid: string }) {
  const { data, isLoading, error } = useApiGet<ContextPayload>(
    ['graph-context', uid],
    `/api/graph/context/${encodeURIComponent(uid)}`,
    { depth: 1, include_content: false, include_evidence: true, include_spine: true },
  );

  if (isLoading) {
    return (
      <div className="p-4 text-sm text-[var(--cos-muted)]">
        <p>loading node…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div role="alert" className="p-4 text-sm text-rose-400">
        {error.message}
      </div>
    );
  }
  if (!data || !data.node) {
    return (
      <div className="p-4 text-sm text-[var(--cos-muted)]">
        <p>node not found: {uid}</p>
      </div>
    );
  }

  const node = data.node;
  const editorUrl = node.file_path
    ? `vscode://file/${encodeURI(node.file_path)}${node.start_line ? `:${node.start_line}` : ''}`
    : null;

  return (
    <div className="flex h-full flex-col overflow-auto p-3 text-sm cos-scroll">
      <header className="mb-3">
        <h2 className="mb-1 flex items-center gap-2 text-base font-semibold">
          <span
            className="inline-block h-3 w-3 rounded-sm"
            style={{ background: kindColor(node.kind) }}
            aria-hidden
          />
          <span className="truncate">{node.label || node.uid}</span>
        </h2>
        <p className="font-mono text-xs text-[var(--cos-muted)]">{node.uid}</p>
      </header>

      {data.spine && data.spine.length > 0 && (
        <section className="mb-3 text-xs">
          <h3 className="mb-1 font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
            Breadcrumbs
          </h3>
          <p className="break-words text-[var(--cos-text)]">
            {data.spine.map((s, i) => (
              <span key={s.uid}>
                {i > 0 && <span className="text-[var(--cos-muted)]"> / </span>}
                <span>{s.label || s.uid}</span>
              </span>
            ))}
          </p>
        </section>
      )}

      <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs">
        <dt className="text-[var(--cos-muted)]">kind</dt>
        <dd>{node.kind}</dd>
        {node.file_path && (
          <>
            <dt className="text-[var(--cos-muted)]">file</dt>
            <dd className="break-all font-mono">
              {node.file_path}
              {node.start_line ? `:${node.start_line}` : ''}
            </dd>
          </>
        )}
        {node.signature && (
          <>
            <dt className="text-[var(--cos-muted)]">sig</dt>
            <dd className="break-words font-mono">{node.signature}</dd>
          </>
        )}
      </dl>

      {node.doc_blob && (
        <section className="mb-3">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
            Doc
          </h3>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-[var(--cos-bg)] p-2 text-xs cos-scroll">
            {node.doc_blob}
          </pre>
        </section>
      )}

      {editorUrl && (
        <a
          href={editorUrl}
          className="mb-3 inline-flex items-center gap-1 self-start rounded border border-[var(--cos-border)] px-2 py-1 text-xs hover:bg-[var(--cos-panel)]"
        >
          <ExternalLink size={12} aria-hidden />
          Open in Editor
        </a>
      )}

      {data.edges_by_type && (
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
            Neighbours
          </h3>
          <ul className="space-y-1 text-xs">
            {Object.entries(data.edges_by_type).map(([edgeType, list]) => (
              <li key={edgeType}>
                <span className="text-[var(--cos-accent)]">{edgeType}</span>
                <ul className="ml-3">
                  {list.slice(0, 8).map((n) => (
                    <li key={`${edgeType}:${n.uid}`} className="truncate">
                      <span
                        className="mr-1 inline-block h-2 w-2 rounded-sm"
                        style={{ background: kindColor(n.kind) }}
                        aria-hidden
                      />
                      {n.label || n.uid}
                    </li>
                  ))}
                  {list.length > 8 && (
                    <li className="text-[var(--cos-muted)]">+{list.length - 8} more</li>
                  )}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
