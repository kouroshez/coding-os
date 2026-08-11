import { Section } from './DoctorPrimitives';
import { ISSUE_LABELS, ISSUE_SEVERITY } from './doctor-shared';
import { StatTile } from '@/lib/charts';
import { useApiGet } from '@/lib/hooks';
import type { GraphDoctorData, GraphDoctorPayload, GraphIssue } from './doctor-types';

export function BackendTab() {
  const doctor = useApiGet<GraphDoctorPayload>(['api-graph-doctor'], '/api/graph/doctor', undefined, {
    refetchIntervalMs: 10000,
  });
  if (doctor.isLoading) return <p className="text-xs text-[var(--cos-muted)]">probing graph backend…</p>;
  if (doctor.error) return <p className="text-xs text-[var(--cos-err)]">{doctor.error.message}</p>;
  const payload = (doctor.data?.data ?? doctor.data ?? {}) as GraphDoctorData;
  if (!payload || Object.keys(payload).length === 0) {
    return <p className="text-xs text-[var(--cos-muted)]">graph_os backend reported no data.</p>;
  }
  const issues = payload.issues ?? [];
  const stats = payload.stats ?? {};
  const healthy = payload.healthy ?? false;
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
      <StatTile
        label="Health"
        value={healthy ? 'OK' : 'attention'}
        tone={healthy ? 'ok' : 'warn'}
      />
      <StatTile label="Nodes" value={stats.node_count ?? '—'} tone="neutral" />
      <StatTile label="Edges" value={stats.edge_count ?? '—'} tone="neutral" />
      <StatTile
        label="Issues"
        value={stats.issue_count ?? issues.length}
        tone={(stats.issue_count ?? issues.length) > 0 ? 'warn' : 'ok'}
      />
      {issues.length === 0 ? (
        <Section title="No issues" cols="md:col-span-4">
          <p className="text-[11px] text-[var(--cos-muted)]">All graph_os health checks pass.</p>
        </Section>
      ) : (
        issues.map((issue) => <IssueCard key={issue.category} issue={issue} />)
      )}
    </div>
  );
}

export function IssueCard({ issue }: { issue: GraphIssue }) {
  const label = ISSUE_LABELS[issue.category] ?? issue.category;
  const sample = issue.sample ?? [];
  // Derive columns from the first sample row; sort by string key so the
  // table layout is stable across renders. Missing keys render `—`.
  const columns = sample.length > 0 ? Object.keys(sample[0]).sort() : [];
  // W7.6: informational issues (e.g. stdlib stub orphans) use a muted
  // amber badge instead of the alarming rose so the user can tell at a
  // glance which categories require action.
  const severity = ISSUE_SEVERITY[issue.category] ?? 'real';
  const badgeClass =
    severity === 'info'
      ? 'rounded bg-[var(--cos-warn-tint)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--cos-warn)]'
      : 'rounded bg-[var(--cos-err-tint)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--cos-err)]';
  return (
    <Section
      title={
        <span className="flex items-center gap-2">
          <span>{label}</span>
          <span className={badgeClass}>
            {issue.count.toLocaleString()}
          </span>
          {severity === 'info' && (
            <span className="text-[10px] text-[var(--cos-muted)]">informational</span>
          )}
        </span>
      }
      cols="md:col-span-2"
    >
      {sample.length === 0 ? (
        <p className="text-[11px] text-[var(--cos-muted)]">no sample available.</p>
      ) : (
        <div className="cos-scroll max-h-64 overflow-auto">
          <table dir="ltr" className="w-full text-[10px]">
            <thead className="text-left text-[var(--cos-muted)]">
              <tr>
                {columns.map((c) => (
                  <th key={c} className="py-1 pr-2 font-normal">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sample.map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => {
                    const v = row[c];
                    const display =
                      v == null
                        ? <span className="text-[var(--cos-faint)]">—</span>
                        : <span className="break-all font-mono">{String(v)}</span>;
                    return (
                      <td
                        key={c}
                        className="border-t border-[var(--cos-border)] py-1 pr-2 align-top"
                      >
                        {display}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

// ----- sqlite (per-project DB row counts) ---------------------------
