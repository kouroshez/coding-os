import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';

// TASK-024: alarm chip in the top bar. Silent when everything is green;
// surfaces a clickable amber pill the moment graph_os reports issues or
// the /health probe degrades. One-glance "is the system broken?" signal
// per the user's Phase-10 ask. Polls every 30 s — light enough to keep
// running on every page without flooding the API.

interface DoctorResp {
  data?: { healthy?: boolean; stats?: { issue_count?: number } };
}
interface HealthResp {
  status?: string;
  backend_id?: string;
}

export default function HealthAlarmBar() {
  const doctor = useApiGet<DoctorResp>(['alarm-doctor'], '/api/graph/doctor', undefined, {
    refetchIntervalMs: 30000,
  });
  const health = useApiGet<HealthResp>(['alarm-health'], '/api/health', undefined, {
    refetchIntervalMs: 30000,
  });

  const issueCount = doctor.data?.data?.stats?.issue_count ?? 0;
  const graphHealthy = doctor.data?.data?.healthy ?? true;
  const healthOk = (health.data?.status ?? 'ok') === 'ok';
  // TASK-027: fetch errors mean the backend is unreachable, which IS the
  // worst kind of degraded state — silently hiding it defeated the bar's
  // whole purpose. Treat any error as alarm-worthy on top of the
  // backend-reported issue checks.
  const backendUnreachable = Boolean(doctor.error || health.error);

  const degraded = backendUnreachable || !graphHealthy || !healthOk || issueCount > 0;
  if (!degraded) return null;

  const summary: string[] = [];
  if (backendUnreachable) summary.push('backend unreachable');
  if (!healthOk) summary.push(`/health: ${health.data?.status ?? '?'}`);
  if (issueCount > 0) summary.push(`${issueCount} graph issue${issueCount === 1 ? '' : 's'}`);
  if (summary.length === 0) summary.push('degraded');

  return (
    <Link
      to="/diagnostics/doctor"
      role="alert"
      aria-label={`system alarm: ${summary.join(', ')}`}
      className="flex items-center gap-1.5 rounded-full bg-amber-900/40 px-2.5 py-1 text-[11px] font-semibold text-amber-200 hover:bg-amber-900/60 transition-colors"
    >
      <AlertTriangle size={12} aria-hidden />
      <span>{summary.join(' · ')}</span>
    </Link>
  );
}
