import { Row, Section } from './DoctorPrimitives';
import { fmtAge } from './doctor-shared';
import { StatTile } from '@/lib/charts';
import type { HealthPayload } from './doctor-types';

export function OverviewTab({
  health,
  loading,
  error,
}: {
  health: HealthPayload | undefined;
  loading: boolean;
  error: Error | null;
}) {
  if (loading) return <p className="text-xs text-[var(--cos-muted)]">probing…</p>;
  if (error) return <p className="text-xs text-[var(--cos-err)]">{error.message}</p>;
  if (!health) return null;

  const indexFreshness = health.file_index_state_last_indexed_at ?? null;
  const isOk = health.status === 'ok';
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile
        label="Backend"
        value={health.backend_id}
        tone={isOk ? 'ok' : 'danger'}
      />
      <StatTile label="Nodes (sample)" value={health.node_count_sample ?? '—'} tone="neutral" />
      <StatTile label="Edges (sample)" value={health.edge_count_sample ?? '—'} tone="neutral" />
      <StatTile
        label="Index rows"
        value={health.file_index_state_rows ?? '—'}
        tone={(health.file_index_state_rows ?? 0) > 0 ? 'ok' : 'warn'}
      />
      <Section title="Index freshness" cols="md:col-span-2">
        <Row k="last indexed" v={fmtAge(indexFreshness)} />
        <Row k="rows" v={String(health.file_index_state_rows ?? 0)} />
        {health.file_index_state_error && (
          <Row k="error" v={health.file_index_state_error} danger />
        )}
      </Section>
      <Section title="Probe sample" cols="md:col-span-2">
        <Row k="edge sample" v={String(health.edge_sample ?? '—')} />
        <Row k="node count sample" v={String(health.node_count_sample ?? '—')} />
        <Row k="edge count sample" v={String(health.edge_count_sample ?? '—')} />
        {health.reason && <Row k="reason" v={health.reason} danger />}
      </Section>
    </div>
  );
}

// ----- Health (charts) ----------------------------------------------
