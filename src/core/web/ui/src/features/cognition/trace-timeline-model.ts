// Wire shapes emitted by thinking_os/tracing.py plus the pure presentation
// maps (colour, label, phase bucket, timestamp) the timeline renders from.

export interface TraceEvent {
  kind?: string;
  ts?: number;
  node?: string;
  role?: string | null;
  phase?: string | null;
  // The producer (thinking_os/tracing.py:112) nests summary/formula_id/
  // status/latency under `data`; only kind/ts/node/role/phase are top-level.
  data?: Record<string, unknown> | null;
  raw?: string;
  [key: string]: unknown;
}

export interface SessionMeta {
  agent?: string;
  session_id?: string;
  sdk_uuid?: string | null;
  pid?: number;
  started_at?: number;
  last_prompt_at?: number;
  last_tool_at?: number;
  last_stop_at?: number | null;
  ended_at?: number | null;
}

export interface TracePayload {
  session_id: string;
  agent?: string | null;
  events: TraceEvent[];
  count: number;
  session?: SessionMeta | null;
  has_trace?: boolean;
  source?: 'trace+session' | 'trace-only' | 'session-only';
}

// Keys MUST match the kinds thinking_os/tracing.py actually emits.
export const EVENT_COLORS: Record<string, string> = {
  classify: '#e0a227',
  analyze_start: '#e0a227',
  analyze_done: '#e0a227',
  compose_done: '#7c82f2',
  dispatch_started: '#3fb950',
  dispatch_completed: '#2e9e6e',
  parallel_dispatch: '#3fb950',
  role_dispatch: '#4c8dff',
  role_output_recorded: '#4c8dff',
  supervise_action: '#4c8dff',
  backtrack: '#f2576b',
  anti_paralysis_warn: '#f0a850',
  task_done: '#2e9e6e',
  error: '#f2576b',
};

export function eventColor(kind: string | undefined): string {
  if (!kind) return '#6c7480';
  return EVENT_COLORS[kind] ?? '#6c7480';
}

export function eventKey(e: TraceEvent, i: number): string {
  return `${i}-${e.kind ?? 'event'}-${e.ts ?? ''}`;
}

// Plain-language labels for cognition event kinds so a non-developer reads
// "what the agent did" instead of OTEL-style internals.
export const KIND_LABEL: Record<string, string> = {
  classify: 'Classified the request',
  analyze_start: 'Started analysing the task',
  analyze_done: 'Finished analysing the task',
  compose_done: 'Composed the role chain',
  dispatch_started: 'Dispatched a sub-agent',
  dispatch_completed: 'Sub-agent finished',
  role_dispatch: 'Ran a role',
  role_output_recorded: 'Recorded role evidence',
  supervise_action: 'Supervised a step',
  parallel_dispatch: 'Ran sub-agents in parallel',
  backtrack: 'Reconsidered (backtrack)',
  anti_paralysis_warn: 'Anti-paralysis nudge',
  task_done: 'Marked the task done',
};

export function humanLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind.replace(/_/g, ' ');
}

export function fmtTime(ts?: number): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString();
}

export function humanDetail(e: TraceEvent): string {
  const d: Record<string, unknown> = e.data ?? {};
  if (d.summary) return String(d.summary);
  const bits: string[] = [];
  if (e.role) bits.push(`role: ${String(e.role)}`);
  if (e.phase) bits.push(`phase: ${String(e.phase)}`);
  if (d.formula_id != null) bits.push(`formula: ${String(d.formula_id)}`);
  if (d.status != null) bits.push(`status: ${String(d.status)}`);
  if (d.latency_ms != null) bits.push(`${String(d.latency_ms)}ms`);
  return bits.join(' · ') || 'no further detail recorded';
}

// Map the producer's flowchart node (tracing.py FLOWCHART_NODES) to a human
// phase so the timeline reads Setup -> Plan -> Execute -> Verify -> Close.
export const PHASE_BY_NODE: Record<string, string> = {
  'n-sinit': 'setup',
  'n-gate': 'setup',
  'n-analyzer': 'plan',
  'n-router': 'plan',
  'n-supervisor': 'execute',
  'n-impl': 'execute',
  'n-ambi': 'verify',
  'n-trace': 'verify',
  'n-verify': 'verify',
  'n-done': 'close',
  'n-end': 'close',
};
export const PHASE_ORDER = ['setup', 'plan', 'execute', 'verify', 'close', 'other'] as const;
export const PHASE_LABEL: Record<string, string> = {
  setup: 'Setup',
  plan: 'Plan',
  execute: 'Execute',
  verify: 'Verify',
  close: 'Close',
  other: 'Other',
};

export function phaseOf(e: TraceEvent): string {
  return PHASE_BY_NODE[e.node ?? ''] ?? 'other';
}
