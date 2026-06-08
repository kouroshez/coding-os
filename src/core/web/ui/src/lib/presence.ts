/**
 * Shared presence shape + humanization helpers for the live-agents surfaces.
 * Field names mirror the producer exactly (web/routes/presence.py:57-71); this
 * is the canonical type so new code stops hand-maintaining divergent copies.
 */

export interface PresenceAgent {
  agent: string;
  session_id?: string | null;
  sdk_uuid?: string | null;
  model?: string | null;
  gate?: string | null;
  task?: string | null;
  skill_active?: string | null;
  role?: string | null;
  chain?: string[];
  state?: string | null;
  context_pct?: number | null;
}

export interface PresenceAgentsResponse {
  agents: PresenceAgent[];
}

export interface AgentStatus {
  label: string;
  dot: string;
  /** true while the agent is doing work (drives the pulsing dot). */
  pulse: boolean;
}

const STATUS: Record<string, AgentStatus> = {
  active: { label: 'Active', dot: '#16a34a', pulse: true },
  working: { label: 'Working', dot: '#16a34a', pulse: true },
  present: { label: 'Idle', dot: '#fbbf24', pulse: false },
  idle: { label: 'Idle', dot: '#fbbf24', pulse: false },
  offline: { label: 'Offline', dot: '#6b7280', pulse: false },
};

export function agentStatus(state?: string | null): AgentStatus {
  return STATUS[state ?? 'offline'] ?? { label: titleCase(state ?? 'unknown'), dot: '#6b7280', pulse: false };
}

/** "claude-opus-4-8[1m]" → "Opus 4.8 · 1M". Falls back to the raw id. */
export function modelLabel(model?: string | null): string {
  if (!model) return 'Unknown runtime';
  const m = model.match(/claude-([a-z]+)-(\d+)-(\d+)(?:\[(\w+)\])?/i);
  if (!m) return model;
  const tier = titleCase(m[1]);
  const ctx = m[4] ? ` · ${m[4].toUpperCase()}` : '';
  return `${tier} ${m[2]}.${m[3]}${ctx}`;
}

const GATE_COLORS: Record<string, string> = {
  CLEAR: '#16a34a',
  COMPLICATED: '#3b82f6',
  COMPLEX: '#f59e0b',
  CHAOTIC: '#ef4444',
  CONFUSION: '#a855f7',
};

export interface GateMeta {
  level: string;
  dims: string | null;
  color: string;
}

/** "COMPLEX 6" → { level: 'Complex', dims: '6', color }. */
export function gateMeta(gate?: string | null): GateMeta | null {
  const raw = (gate ?? '').trim();
  if (!raw) return null;
  const [levelRaw, dimsRaw] = raw.split(/\s+/);
  const up = (levelRaw ?? '').toUpperCase();
  return { level: titleCase(up), dims: dimsRaw ?? null, color: GATE_COLORS[up] ?? '#6b7280' };
}

function titleCase(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}
