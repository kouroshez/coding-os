import type { Tab } from './doctor-types';

export const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'health', label: 'Health & charts' },
  { id: 'maintenance', label: 'Maintenance' },
  { id: 'backend', label: 'Knowledge graph' },
  { id: 'sqlite', label: 'SQLite' },
];

export const MAX_SAMPLES = 60; // 2 minutes at 2s/poll

// Routes the SPA hits on its own timers (presence beacons, hook feeds, the
// Doctor page's own health/metrics polling). Excluded from the charts by
// default so an idle hub reads as idle — the counters otherwise climb from
// the dashboard measuring itself.
export const SELF_POLL_ROUTES = new Set([
  'presence.agents',
  'presence.now',
  'hooks.recent',
  'hooks.stream',
  'sessions.active',
  'logs.summary',
  'board.list',
  'cognition.chats',
  'cognition.traces',
  'graph.doctor',
  'health',
  'health.db',
  'metrics',
]);


export function fmtAge(epoch: number | null | undefined): string {
  if (!epoch) return '—';
  const diff = Math.max(0, Math.floor(Date.now() / 1000) - epoch);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function fmtMs(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  if (seconds < 0.001) return `${(seconds * 1_000_000).toFixed(0)}µs`;
  if (seconds < 1) return `${(seconds * 1000).toFixed(1)}ms`;
  return `${seconds.toFixed(2)}s`;
}



export const ISSUE_LABELS: Record<string, string> = {
  dangling_source: 'Dangling source edges',
  dangling_target: 'Dangling target edges',
  // W7.6: legacy `orphaned_nodes` split into in-repo (real bugs) vs
  // external-unresolved (informational stdlib stubs).
  orphaned_nodes: 'Orphaned nodes (legacy)',
  orphaned_inrepo: 'Orphaned in-repo nodes',
  orphaned_external_unresolved: 'Unresolved external stubs (info)',
  malformed_uid_path: 'Malformed UID paths',
  self_loops: 'Self-loops',
  duplicate_edges: 'Duplicate edges',
  stale_paths: 'Stale paths',
  files_with_parse_errors: 'Files no extractor could read (info)',
  slowest_extractions: 'Slowest files to index (info)',
};
// Anything absent here renders as a real defect, so a category added to the
// backend without a row below arrives looking like breakage under a raw
// snake_case key. Both rows here are expected states, not faults: unrendered
// scaffold templates ({{VAR}} is not valid YAML) and languages with no
// extractor yet land in parse errors, and slow files are a timing report.
export const ISSUE_SEVERITY: Record<string, 'real' | 'info'> = {
  orphaned_external_unresolved: 'info',
  files_with_parse_errors: 'info',
  slowest_extractions: 'info',
};

export function doctorDotClass(status: string): string {
  switch (status) {
    case 'ok': return 'bg-[var(--cos-ok-tint)]';
    case 'degraded': return 'bg-[var(--cos-warn-tint)]';
    case 'error': return 'bg-[var(--cos-err-tint)]';
    default: return 'bg-[var(--cos-panel)]';
  }
}

// ----- Overview ------------------------------------------------------
