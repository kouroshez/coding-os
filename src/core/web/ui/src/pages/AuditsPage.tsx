import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

interface AuditRow {
  audit_id: string;
  task_id?: string;
  status: string;
  predicates: string[];
  matched_exhaustive: string[];
  matched_scope: string[];
  rows_total: number;
  rows_unchecked: number;
  path: string;
}

interface AuditsEnvelope {
  ok: boolean;
  data: { audits: AuditRow[]; count: number };
}

function api(slug: string | undefined, path: string): string {
  const base = slug ? `/api/p/${slug}` : '/api';
  return `${base}${path}`;
}

export default function AuditsPage() {
  const { slug } = useParams<{ slug?: string }>();
  const [audits, setAudits] = useState<AuditRow[]>([]);
  const [filter, setFilter] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = filter ? `?status=${encodeURIComponent(filter)}` : '';
    fetch(api(slug, `/audits${qs}`))
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<AuditsEnvelope>;
      })
      .then((env) => {
        if (cancelled) return;
        setAudits(env.data?.audits ?? []);
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
        <h1 className="text-xl font-semibold">Active Audits</h1>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="border rounded px-2 py-1 text-sm"
        >
          <option value="">All statuses</option>
          <option value="in_progress">In progress</option>
          <option value="completed">Completed</option>
        </select>
      </header>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}
      {error && (
        <div className="text-sm text-red-600">Failed to load audits: {error}</div>
      )}
      {!loading && !error && audits.length === 0 && (
        <div className="text-sm text-gray-500">
          No audits found. They appear when a user prompt triggers exhaustive
          intent and the agent writes a docs/tasks/audits/audit-*.md artifact.
        </div>
      )}

      {audits.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2 pr-4">Audit</th>
              <th className="py-2 pr-4">Task</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Progress</th>
              <th className="py-2 pr-4">Predicates</th>
              <th className="py-2 pr-4">Path</th>
            </tr>
          </thead>
          <tbody>
            {audits.map((a) => {
              const done = a.rows_total - a.rows_unchecked;
              const pct = a.rows_total ? Math.round((done / a.rows_total) * 100) : 0;
              return (
                <tr key={a.audit_id} className="border-b">
                  <td className="py-2 pr-4 font-mono">{a.audit_id}</td>
                  <td className="py-2 pr-4">{a.task_id ?? '—'}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={
                        a.status === 'in_progress'
                          ? 'text-amber-600'
                          : a.status === 'completed'
                          ? 'text-emerald-600'
                          : 'text-gray-500'
                      }
                    >
                      {a.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4">
                    <div className="flex items-center gap-2">
                      <div className="w-32 h-2 bg-gray-200 rounded">
                        <div
                          className="h-2 bg-emerald-500 rounded"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-600">
                        {done}/{a.rows_total} ({pct}%)
                      </span>
                    </div>
                  </td>
                  <td className="py-2 pr-4 text-xs">
                    {(a.predicates ?? []).join(', ')}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs">{a.path}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
