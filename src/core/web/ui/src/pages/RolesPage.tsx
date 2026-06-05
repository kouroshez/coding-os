import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';

interface RoleDef {
  formula_id: string;
  role_name: string;
  output_schema: string;
  schema_json: Record<string, unknown> | null;
  version: string;
}

interface RolesPayload {
  roles: RoleDef[];
  count: number;
  dispatch_available?: boolean;
}

interface ChainPayload {
  agent: string;
  chain: string[];
  active_formula: string | null;
  has_active_session: boolean;
}

interface RoleOutput {
  session_id: string;
  agent: string;
  ts?: number;
  status?: string;
  latency_ms?: number;
  output_hash?: string;
  output_json?: unknown;
  schema_ok?: boolean | null;
  schema_status?: 'ok' | 'fail' | 'no_payload' | 'no_schema' | 'planned';
  schema_errors?: string[];
  chain?: string[];
  preset_id?: string | null;
}

interface RoleOutputsPayload {
  formula_id: string;
  outputs: RoleOutput[];
  count: number;
  executed_count?: number;
  planned_count?: number;
}

function formatTs(ts?: number): string {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString();
}

export default function RolesPage() {
  const { slug } = useParams<{ slug?: string }>();
  const [agent, setAgent] = useState('claude');
  const { data: rolesData, isLoading: rolesLoading } = useApiGet<RolesPayload>(
    ['roles-list'],
    '/api/roles',
  );
  const [selected, setSelected] = useState<string | null>(null);

  const roles = rolesData?.roles ?? [];
  const dispatchAvailable = rolesData?.dispatch_available ?? false;
  const selectedRole = useMemo(() => {
    if (!roles.length) return null;
    const target = selected ?? roles[0].formula_id;
    return roles.find((r) => r.formula_id === target) ?? roles[0];
  }, [roles, selected]);

  const { data: chainData } = useApiGet<ChainPayload>(
    ['roles-chain', agent],
    '/api/roles/chain',
    { agent },
  );

  const { data: outputData, isLoading: outputLoading } = useApiGet<RoleOutputsPayload>(
    ['roles-outputs', selectedRole?.formula_id ?? '', agent],
    selectedRole ? `/api/roles/${encodeURIComponent(selectedRole.formula_id)}/outputs` : '/api/roles/F1/outputs',
    { agent, limit: 20 },
    { enabled: Boolean(selectedRole) },
  );

  return (
    <div className="grid h-full" style={{ gridTemplateColumns: '320px 280px 1fr' }}>
      <aside className="border-r border-[var(--cos-border)] bg-[var(--cos-panel)] overflow-auto cos-scroll">
        <header className="border-b border-[var(--cos-border)] px-3 py-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">Formulas</h2>
        </header>
        {rolesLoading && <p className="p-3 text-xs text-[var(--cos-muted)]">loading roles...</p>}
        <ul>
          {roles.map((role) => {
            const active = selectedRole?.formula_id === role.formula_id;
            return (
              <li key={role.formula_id}>
                <button
                  type="button"
                  onClick={() => setSelected(role.formula_id)}
                  className={[
                    'w-full border-b border-[var(--cos-border)] px-3 py-2 text-left',
                    active ? 'bg-[var(--cos-accent)]/15' : 'hover:bg-[var(--cos-accent)]/5',
                  ].join(' ')}
                >
                  <div className="text-xs font-semibold">
                    {role.formula_id} - {role.role_name}
                  </div>
                  <div className="mt-1 text-[10px] text-[var(--cos-muted)]">
                    {role.version} - {role.output_schema}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <section className="border-r border-[var(--cos-border)] bg-[var(--cos-bg)]">
        <header className="border-b border-[var(--cos-border)] px-3 py-2 text-xs">
          <div className="font-semibold uppercase tracking-wide text-[var(--cos-muted)]">Composed Chain</div>
          <div className="mt-2 flex items-center gap-2">
            <label className="text-[10px] text-[var(--cos-muted)]" htmlFor="roles-agent">
              Agent
            </label>
            <select
              id="roles-agent"
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-1.5 py-1 text-[11px]"
            >
              <option value="claude">claude</option>
              <option value="codex">codex</option>
              <option value="cursor">cursor</option>
            </select>
          </div>
        </header>
        <div className="p-3 text-xs">
          {!chainData?.has_active_session && (
            <p className="text-[var(--cos-muted)]">
              No composed chain yet - appears once a COMPLICATED/COMPLEX task auto-composes a chain (or a `cos_compose_chain` call).
            </p>
          )}
          <ol className="space-y-0">
            {(chainData?.chain ?? []).map((fid, i, arr) => {
              const isActive = fid === chainData?.active_formula;
              const name = fid.charAt(0).toUpperCase() + fid.slice(1).replace(/_/g, ' ');
              return (
                <li key={fid} className="relative flex items-start gap-3 pb-3 last:pb-0">
                  {i < arr.length - 1 && (
                    <span
                      aria-hidden
                      className="absolute left-[11px] top-6 bottom-0 w-px bg-[var(--cos-border)]"
                    />
                  )}
                  <span
                    className={[
                      'relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold',
                      isActive
                        ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)] text-[var(--cos-bg)]'
                        : 'border-[var(--cos-border)] bg-[var(--cos-panel)] text-[var(--cos-muted)]',
                    ].join(' ')}
                  >
                    {i + 1}
                  </span>
                  <div className="pt-0.5">
                    <div
                      className={
                        isActive
                          ? 'text-[13px] font-semibold text-[var(--cos-text)]'
                          : 'text-[13px] text-[var(--cos-muted)]'
                      }
                    >
                      {name}
                    </div>
                    {isActive && (
                      <div className="mt-0.5 inline-flex items-center gap-1 text-[10px] text-[var(--cos-accent)]">
                        <span className="h-1.5 w-1.5 rounded-full bg-[var(--cos-accent)]" />
                        active · {i + 1}/{arr.length}
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </section>

      <section className="overflow-auto cos-scroll">
        <header className="border-b border-[var(--cos-border)] px-4 py-2 text-xs">
          <h2 className="font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
            Evidence ({selectedRole?.formula_id ?? '-'})
          </h2>
          <p className="text-[var(--cos-muted)]">
            {outputData?.planned_count ?? 0} composed (in-session) · {outputData?.executed_count ?? 0} dispatched (sub-agent)
          </p>
          <p className="mt-1 text-[10px]">
            <span className="text-[var(--cos-muted)]">Sub-agent dispatch: </span>
            {dispatchAvailable ? (
              <span className="text-[var(--cos-ok)]">enabled</span>
            ) : (
              <span className="text-[var(--cos-muted)]">disabled — in-session only (Claude SDK extra not installed)</span>
            )}
          </p>
        </header>
        {outputLoading && <p className="p-4 text-sm text-[var(--cos-muted)]">loading outputs...</p>}
        {!outputLoading && (outputData?.outputs?.length ?? 0) === 0 && (
          <div className="m-4 rounded border border-dashed border-[var(--cos-border)] bg-[var(--cos-panel)] p-4 text-sm">
            <p className="font-semibold text-[var(--cos-text)]">
              No composed chain references <span className="font-mono">{selectedRole?.formula_id}</span> yet.
            </p>
            <p className="mt-2 text-[12px] leading-relaxed text-[var(--cos-muted)]">
              Roles are composed automatically for COMPLICATED/COMPLEX tasks (or via
              <code className="mx-1 rounded bg-[var(--cos-bg)] px-1 py-0.5 font-mono text-[11px] text-[var(--cos-accent)]">cos_compose_chain</code>).
              Each chain member then shows here as
              <span className="mx-1 text-[var(--cos-warn)]">composed</span> — in single-agent mode the
              agent plays the role in-session, so "composed" is the expected state, not a gap. A
              <span className="mx-1 text-[var(--cos-ok)]">dispatched</span> row with recorded evidence
              appears only when a role runs as a separate sub-agent via
              <code className="mx-1 rounded bg-[var(--cos-bg)] px-1 py-0.5 font-mono text-[11px] text-[var(--cos-accent)]">cos_supervise_record_output</code>
              (the SDK dispatch path).
            </p>
            <p className="mt-3 text-[11px] text-[var(--cos-muted)]">
              Selected agent: <span className="font-mono">{agent}</span> · switch above to
              check other agents, or visit the Cognition tab to inspect raw traces.
            </p>
          </div>
        )}
        <ol className="p-3 space-y-2">
          {outputData?.outputs.map((row) => {
            const link = slug
              ? `/p/${encodeURIComponent(slug)}/cognition/${encodeURIComponent(row.session_id)}`
              : `/cognition/${encodeURIComponent(row.session_id)}`;
            const isPlanned = row.status === 'planned';
            return (
              <li
                key={`${row.agent}:${row.session_id}:${row.output_hash ?? row.ts ?? 'planned'}`}
                className={[
                  'rounded border p-2',
                  isPlanned
                    ? 'border-[var(--cos-warn)] bg-[var(--cos-warn-tint)]'
                    : 'border-[var(--cos-border)]',
                ].join(' ')}
              >
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono font-semibold">{row.agent}</span>
                  <span className="text-[var(--cos-muted)]">{formatTs(row.ts)}</span>
                  {isPlanned && (
                    <span className="rounded bg-[var(--cos-warn-tint)] px-1 text-[10px] text-[var(--cos-warn)]">
                      composed · in-session
                    </span>
                  )}
                  {typeof row.schema_ok === 'boolean' && (
                    <span
                      className={[
                        'rounded px-1 text-[10px]',
                        row.schema_ok ? 'bg-[var(--cos-ok-tint)] text-[var(--cos-ok)]' : 'bg-[var(--cos-err-tint)] text-[var(--cos-err)]',
                      ].join(' ')}
                    >
                      {row.schema_ok ? 'schema ok' : 'schema fail'}
                    </span>
                  )}
                  <Link to={link} className="ml-auto text-[var(--cos-accent)] hover:underline">
                    open trace
                  </Link>
                </div>
                {isPlanned ? (
                  <div className="mt-1 text-[10px] text-[var(--cos-muted)]">
                    chain: <span className="font-mono">{(row.chain ?? []).join(' → ')}</span>
                    {row.preset_id && (
                      <>
                        {' '}· preset:{' '}
                        <span className="font-mono">{row.preset_id}</span>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="mt-1 text-[10px] text-[var(--cos-muted)]">
                    status: {row.status ?? '-'} · latency: {row.latency_ms ?? 0}ms
                  </div>
                )}
                {row.schema_status === 'no_payload' && !isPlanned && (
                  <div className="mt-1 text-[10px] text-[var(--cos-warn)]">
                    schema n/a: output payload missing from the evidence bundle for this session.
                  </div>
                )}
                {row.schema_status === 'no_schema' && !isPlanned && (
                  <div className="mt-1 text-[10px] text-[var(--cos-warn)]">
                    schema n/a: this role has no registered Output schema.
                  </div>
                )}
                {row.schema_errors && row.schema_errors.length > 0 && (
                  <pre className="mt-2 overflow-auto rounded bg-[var(--cos-panel)] p-2 text-[10px] text-[var(--cos-err)] cos-scroll">
                    {row.schema_errors.join('\n')}
                  </pre>
                )}
                {row.output_json != null && (
                  <pre dir="ltr" className="mt-2 overflow-auto rounded bg-[var(--cos-panel)] p-2 text-[10px] text-[var(--cos-muted)] cos-scroll">
                    {JSON.stringify(row.output_json, null, 2)}
                  </pre>
                )}
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
