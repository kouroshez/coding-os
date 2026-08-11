import { useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';
import type { HealthPayload, Tab } from './doctor/doctor-types';
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
  return (
    <PageShell>
      <PageHeader
        eyebrow={
          <StatusPill
            label={`doctor · ${health.data?.status ?? 'probing…'}`}
            dotColor={health.data ? doctorDotClass(health.data.status) : 'bg-[var(--cos-panel)]'}
          />
        }
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
