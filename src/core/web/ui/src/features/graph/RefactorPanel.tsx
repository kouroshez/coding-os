import { useState } from 'react';
import { apiGet } from '@/lib/api-client';
import { useApiGet } from '@/lib/hooks';

// Producer shapes verified live against the emit sites:
// /api/graph/rename-plan/{uid} ← cos_graph_rename_plan
// /api/graph/contracts         ← cos_graph_contracts
interface RenameEdge {
  source_uid: string;
  target_uid: string;
}
interface StringLiteral {
  file: string;
  line: number;
  text: string;
}
interface RenamePlanPayload {
  old_name: string;
  new_name: string;
  uid: string;
  call_sites: RenameEdge[];
  call_sites_total_count: number;
  doc_references: RenameEdge[];
  doc_references_total_count: number;
  test_references: RenameEdge[];
  test_references_total_count: number;
  string_literals: StringLiteral[];
  risk: string;
  suggested_order: string;
  confidence: number;
}
interface ContractRow {
  uid: string;
  kind: string;
  label: string;
  file_path?: string;
  start_line?: number;
}
interface ContractsPayload {
  http_routes: ContractRow[];
  mcp_tools: ContractRow[];
  grpc_endpoints: ContractRow[];
  event_handlers: ContractRow[];
  websocket: ContractRow[];
  count: number;
}

function TouchpointGroup({
  title,
  shown,
  total,
  render,
}: {
  title: string;
  shown: number;
  total: number;
  render: React.ReactNode;
}) {
  return (
    <section className="mb-3">
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        {title} · {total}
        {shown < total && (
          <span className="ml-1 normal-case text-[var(--cos-warn)]">
            (showing {shown} — truncated)
          </span>
        )}
      </h4>
      {render}
    </section>
  );
}

function uidTail(uid: string): string {
  return uid.split('/').pop() ?? uid;
}

export function RenamePlanSection({ uid }: { uid: string }) {
  const [newName, setNewName] = useState('');
  const [plan, setPlan] = useState<RenamePlanPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPlan = async () => {
    if (!newName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const [data] = await apiGet<RenamePlanPayload>(
        `/api/graph/rename-plan/${encodeURIComponent(uid)}`,
        { new_name: newName.trim() },
      );
      setPlan(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'rename-plan failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="text-xs">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void fetchPlan();
        }}
        className="mb-3 flex items-center gap-2"
      >
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="new name…"
          aria-label="New symbol name"
          className="w-36 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
        />
        <button
          type="submit"
          disabled={!newName.trim() || loading}
          className="rounded border border-[var(--cos-accent)] px-2 py-1 font-mono text-xs text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'planning…' : 'plan rename'}
        </button>
      </form>
      {error && (
        <p role="alert" className="mb-2 text-[var(--cos-err)]">
          {error}
        </p>
      )}
      {plan && (
        <>
          <p className="mb-2 text-[var(--cos-muted)]">
            risk: <span className="text-[var(--cos-text)]">{plan.risk}</span> · order:{' '}
            <span className="text-[var(--cos-text)]">{plan.suggested_order}</span>
          </p>
          <TouchpointGroup
            title="call sites"
            shown={plan.call_sites.length}
            total={plan.call_sites_total_count}
            render={
              <ul className="space-y-0.5 font-mono">
                {plan.call_sites.map((e) => (
                  <li key={e.source_uid} className="truncate" title={e.source_uid}>
                    {uidTail(e.source_uid)}
                  </li>
                ))}
                {plan.call_sites.length === 0 && <li className="text-[var(--cos-faint)]">none</li>}
              </ul>
            }
          />
          <TouchpointGroup
            title="doc references"
            shown={plan.doc_references.length}
            total={plan.doc_references_total_count}
            render={
              <ul className="space-y-0.5 font-mono">
                {plan.doc_references.map((e) => (
                  <li key={e.source_uid} className="truncate" title={e.source_uid}>
                    {uidTail(e.source_uid)}
                  </li>
                ))}
                {plan.doc_references.length === 0 && (
                  <li className="text-[var(--cos-faint)]">none</li>
                )}
              </ul>
            }
          />
          <TouchpointGroup
            title="test references"
            shown={plan.test_references.length}
            total={plan.test_references_total_count}
            render={
              <ul className="space-y-0.5 font-mono">
                {plan.test_references.map((e) => (
                  <li key={e.source_uid} className="truncate" title={e.source_uid}>
                    {uidTail(e.source_uid)}
                  </li>
                ))}
                {plan.test_references.length === 0 && (
                  <li className="text-[var(--cos-faint)]">none</li>
                )}
              </ul>
            }
          />
          <TouchpointGroup
            title="string literals"
            shown={plan.string_literals.length}
            total={plan.string_literals.length}
            render={
              <ul className="space-y-0.5 font-mono">
                {plan.string_literals.map((s) => (
                  <li key={`${s.file}:${s.line}`} className="truncate" title={s.text}>
                    {s.file}:{s.line}
                  </li>
                ))}
                {plan.string_literals.length === 0 && (
                  <li className="text-[var(--cos-faint)]">none</li>
                )}
              </ul>
            }
          />
        </>
      )}
    </div>
  );
}

export function ContractsSection() {
  const { data, isLoading, error } = useApiGet<ContractsPayload>(
    ['graph-contracts'],
    '/api/graph/contracts',
  );

  if (isLoading) return <p className="text-xs text-[var(--cos-muted)]">loading contracts…</p>;
  if (error)
    return (
      <p role="alert" className="text-xs text-[var(--cos-err)]">
        {error.message}
      </p>
    );
  if (!data) return <p className="text-xs text-[var(--cos-faint)]">no contract data</p>;

  const groups: Array<[string, ContractRow[]]> = [
    ['HTTP routes', data.http_routes],
    ['MCP tools', data.mcp_tools],
    ['gRPC', data.grpc_endpoints],
    ['Event handlers', data.event_handlers],
    ['WebSocket', data.websocket],
  ];
  return (
    <div className="text-xs">
      <p className="mb-2 text-[var(--cos-muted)]">{data.count} contract nodes</p>
      {groups
        .filter(([, rows]) => rows.length > 0)
        .map(([title, rows]) => (
          <section key={title} className="mb-3">
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
              {title} · {rows.length}
            </h4>
            <ul className="space-y-0.5 font-mono">
              {rows.map((r) => (
                <li key={r.uid} className="truncate" title={`${r.file_path ?? ''}:${r.start_line ?? ''}`}>
                  {r.label}
                </li>
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
}

export default function RefactorPanel({ uid }: { uid: string }) {
  return (
    <div className="p-1">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        Rename plan
      </h3>
      <RenamePlanSection uid={uid} />
      <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        Contract surface
      </h3>
      <ContractsSection />
    </div>
  );
}
