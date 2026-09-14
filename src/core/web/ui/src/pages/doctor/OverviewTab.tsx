import { Row, Section } from './DoctorPrimitives';
import { fmtAge } from './doctor-shared';
import { StatTile } from '@/lib/charts';
import { useApiGet } from '@/lib/hooks';
import type { GraphDoctorData, GraphDoctorPayload, HealthPayload } from './doctor-types';

// The probe walks a bounded prefix of the graph to prove the backend answers.
// Its 101 nodes are a reachability result, never a census: the tiles below
// carry the real totals, and the probe row says how far it got and of what.
const count = (value: number | null | undefined) =>
  value == null ? '—' : value.toLocaleString('en-US');

export function OverviewTab({
  health,
  loading,
  error,
}: {
  health: HealthPayload | undefined;
  loading: boolean;
  error: Error | null;
}) {
  const doctor = useApiGet<GraphDoctorPayload>(['api-graph-doctor'], '/api/graph/doctor', undefined, {
    refetchIntervalMs: 10000,
  });

  if (loading) return <p className="text-xs text-[var(--cos-muted)]">probing…</p>;
  if (error) return <p className="text-xs text-[var(--cos-err)]">{error.message}</p>;
  if (!health) return null;

  const graph = (doctor.data?.data ?? doctor.data ?? {}) as GraphDoctorData;
  const stats = graph.stats ?? {};
  const nodeTotal = stats.node_count ?? null;
  const notes = stats.issue_count_total ?? graph.issues?.length ?? 0;
  const blocking = stats.issue_count ?? 0;
  const backendOk = health.status === 'ok';

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile label="Backend" value={health.backend_id} tone={backendOk ? 'ok' : 'danger'} />
      <StatTile label="Graph nodes" value={count(nodeTotal)} tone="neutral" />
      <StatTile label="Graph edges" value={count(stats.edge_count)} tone="neutral" />
      <StatTile
        label="Indexed files"
        value={count(health.file_index_state_rows)}
        tone={(health.file_index_state_rows ?? 0) > 0 ? 'ok' : 'warn'}
      />

      <Section title="Index freshness" cols="md:col-span-2">
        <Row k="last indexed" v={fmtAge(health.file_index_state_last_indexed_at ?? null)} />
        <Row
          k="refreshed by"
          v={health.file_index_state_last_indexed_at ? 'PostToolUse reindex' : 'never run'}
        />
        {health.file_index_state_error && <Row k="error" v={health.file_index_state_error} danger />}
      </Section>

      <Section title="Backend probe" cols="md:col-span-2">
        <Row
          k="reachability"
          v={
            health.node_count_sample == null
              ? '—'
              : nodeTotal == null
                ? `reached ${count(health.node_count_sample)} nodes`
                : `reached ${count(health.node_count_sample)} of ${count(nodeTotal)} nodes`
          }
        />
        <Row k="probe depth" v={`${count(health.edge_count_sample)} edges walked`} />
        {health.reason && <Row k="reason" v={health.reason} danger />}
      </Section>

      <Section title="Graph health" cols="md:col-span-4">
        {doctor.isLoading ? (
          <Row k="graph_os" v="probing…" />
        ) : (
          <>
            <Row
              k="blocking issues"
              v={blocking === 0 ? 'none' : String(blocking)}
              danger={blocking > 0}
            />
            <Row k="informational notes" v={notes === 0 ? 'none' : String(notes)} />
            <Row
              k="parse errors"
              v={
                stats.parse_error_total
                  ? `${count(stats.parse_error_total)} across ${count(stats.files_with_parse_errors)} file(s)`
                  : 'none'
              }
            />
            <Row k="orphaned nodes" v={count(stats.orphaned_inrepo ?? stats.orphaned_nodes ?? 0)} />
            <Row k="slowest extraction" v={stats.slowest_extraction_ms ? `${count(stats.slowest_extraction_ms)} ms` : '—'} />
            {notes > 0 && (
              // Name the tab as the nav labels it — TABS maps id 'backend' to
              // "Knowledge graph", and pointing a reader at a tab that is not
              // on screen is worse than saying nothing.
              <Row k="detail" v="Knowledge graph tab lists every category with samples" />
            )}
          </>
        )}
      </Section>
    </div>
  );
}
