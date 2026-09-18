import { useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';
import type { GraphDoctorData, GraphDoctorPayload, HealthPayload, Tab } from './doctor/doctor-types';
import { TABS, doctorDotClass } from './doctor/doctor-shared';
import { BackendTab } from './doctor/BackendTab';
import { SqliteTab } from './doctor/SqliteTab';
import { OverviewTab } from './doctor/OverviewTab';
import { HealthTab } from './doctor/HealthTab';
import { MaintenanceTab } from './doctor/MaintenanceTab';

export default function DoctorPage() {
  const [tab, setTab] = useState<Tab>('overview');
  // Project-scoped via api-client rewrite — on /p/<slug>/doctor this
  // becomes /api/p/<slug>/health and the middleware swaps the DB.
  const health = useApiGet<HealthPayload>(['api-health'], '/api/health', undefined, {
    refetchIntervalMs: 5000,
  });
  // The pill used to read /api/health alone, which probes the backend
  // connection and nothing else — so it announced `doctor · ok` on the same
  // screen where the app header warned about a graph issue. One of the two was
  // always wrong to a reader. The pill now names the worse of the two, and
  // when they disagree it says which half is unhappy.
  const graphDoctor = useApiGet<GraphDoctorPayload>(
    ['api-graph-doctor'],
    '/api/graph/doctor',
    undefined,
    { refetchIntervalMs: 10000 },
  );
  const graph = (graphDoctor.data?.data ?? graphDoctor.data ?? {}) as GraphDoctorData;
  const graphIssues = graph.stats?.issue_count ?? 0;
  const backendStatus = health.data?.status;
  const pillStatus = !backendStatus
    ? 'probing…'
    : backendStatus !== 'ok'
      ? backendStatus
      : graphIssues > 0
        ? `graph: ${graphIssues} issue${graphIssues === 1 ? '' : 's'}`
        : 'ok';
  const pillDot = !backendStatus
    ? 'bg-[var(--cos-panel)]'
    : doctorDotClass(backendStatus === 'ok' && graphIssues > 0 ? 'degraded' : backendStatus);
  return (
    <PageShell>
      <PageHeader
        eyebrow={<StatusPill label={`doctor · ${pillStatus}`} dotColor={pillDot} />}
        title="Doctor"
        subtitle="Health probe, dependency checks, and maintenance runners. Auto-refreshes every 5 s."
      />
      <nav
        className="mb-5 flex flex-wrap gap-2 rounded-full border border-[var(--cos-border)] bg-[var(--cos-panel)]/70 p-1 backdrop-blur"
        aria-label="Doctor tabs"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            aria-pressed={tab === t.id}
            className={[
              'rounded-full px-4 py-1.5 text-xs font-medium transition-all',
              tab === t.id
                ? 'bg-[var(--accent)] text-[var(--cos-bg)] shadow-md shadow-[var(--accent)]/20'
                : 'text-[var(--cos-muted)] hover:bg-[var(--cos-panel)] hover:text-[var(--cos-text)]',
            ].join(' ')}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div className="p-1">
        {tab === 'overview' && <OverviewTab health={health.data} loading={health.isLoading} error={health.error} />}
        {tab === 'health' && <HealthTab />}
        {tab === 'maintenance' && <MaintenanceTab health={health.data} />}
        {tab === 'backend' && <BackendTab />}
        {tab === 'sqlite' && <SqliteTab />}
      </div>
    </PageShell>
  );
}

// ----- Backend (graph) ----------------------------------------------
// Render `cos_graph_doctor` output as structured cards instead
// of a raw JSON dump. The top grid surfaces flat stats (healthy,
// node/edge counts), and each issue category from `issues[]` becomes
// its own card with a count badge + sortable sample table.
