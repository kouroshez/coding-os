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
interface LogSummaryResp {
  data?: { error_count?: number; fatal_count?: number };
}

export default function HealthAlarmBar() {
  const doctor = useApiGet<DoctorResp>(['alarm-doctor'], '/api/graph/doctor', undefined, {
    refetchIntervalMs: 30000,
  });
  const health = useApiGet<HealthResp>(['alarm-health'], '/api/health', undefined, {
    refetchIntervalMs: 30000,
  });
  // Observability eye (E11): recent ERROR/FATAL from the durable log feed are
  // the most direct "system is broken" signal — a green graph + green /health
  // while errors pour in is exactly the blind spot the eye exists to close.
  const logs = useApiGet<LogSummaryResp>(['alarm-logs'], '/api/logs/summary', { since: '1h' }, {
    refetchIntervalMs: 30000,
  });

  const issueCount = doctor.data?.data?.stats?.issue_count ?? 0;
  const graphHealthy = doctor.data?.data?.healthy ?? true;
  const healthOk = (health.data?.status ?? 'ok') === 'ok';
  const errorCount = logs.data?.data?.error_count ?? 0;
  const fatalCount = logs.data?.data?.fatal_count ?? 0;
  // TASK-027: fetch errors mean the backend is unreachable, which IS the
  // worst kind of degraded state — silently hiding it defeated the bar's
  // whole purpose. Treat any error as alarm-worthy on top of the
  // backend-reported issue checks.
  const backendUnreachable = Boolean(doctor.error || health.error);

  const degraded =
    backendUnreachable || !graphHealthy || !healthOk || issueCount > 0 || errorCount > 0;
  if (!degraded) return null;

  const summary: string[] = [];
  if (backendUnreachable) summary.push('backend unreachable');
  if (!healthOk) summary.push(`/health: ${health.data?.status ?? '?'}`);
  if (issueCount > 0) summary.push(`${issueCount} graph issue${issueCount === 1 ? '' : 's'}`);
  if (fatalCount > 0) summary.push(`${fatalCount} FATAL (1h)`);
  else if (errorCount > 0) summary.push(`${errorCount} error${errorCount === 1 ? '' : 's'} (1h)`);
  if (summary.length === 0) summary.push('degraded');

  // Red when a FATAL is present (the error storm the user asked to surface);
  // amber for warnings / graph issues otherwise.
  const tone =
    fatalCount > 0
      ? 'bg-[var(--cos-err-tint)] text-[var(--cos-err)] hover:bg-[var(--cos-err-tint)]'
      : 'bg-[var(--cos-warn-tint)] text-[var(--cos-warn)] hover:bg-[var(--cos-warn-tint)]';

  return (
    <Link
      to="/diagnostics/doctor"
      role="alert"
      aria-label={`system alarm: ${summary.join(', ')}`}
      className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${tone}`}
    >
      <AlertTriangle size={12} aria-hidden />
      <span>{summary.join(' · ')}</span>
    </Link>
  );
}
