// ─────────────────────────────────────────────────────────────────────────
// Types — minimal slice of each upstream payload that the dashboard reads.
// ─────────────────────────────────────────────────────────────────────────

export interface PresenceAgent {
  agent: string;
  session_id?: string | null;
  task?: string | null;
  skill_active?: string | null;
  model?: string | null;
  gate?: string | null;
  session?: {
    started_at?: number | null;
    last_tool_at?: number | null;
    last_prompt_at?: number | null;
    pid?: number | null;
  } | null;
}
export interface PresencePayload {
  agents: PresenceAgent[];
  agent_states: Record<string, string>;
  last_hook: HookEvent | null;
  current_chat_uuid: string | null;
}

// Producer: /api/presence/agents (presence.py::presence_agents) — the
// context-window fill the hub-architecture spec documents (TASK-324).
export interface ContextAgent {
  agent: string;
  session_id?: string | null;
  context_pct: number | null;
  used_tokens?: number | null;
  context_window?: number | null;
}
export interface ContextAgentsPayload {
  agents: ContextAgent[];
}

export interface ActiveSession {
  agent: string;
  session_id: string;
  pid: number | null;
  started_at: number | null;
  last_prompt_at: number | null;
  last_tool_at: number | null;
  last_stop_at: number | null;
  ended_at: number | null;
  state: 'active' | 'present' | 'idle' | 'offline' | 'ended';
  is_current?: boolean;
  model?: string | null;
  // Per-session context fill stamped by /api/sessions/active (TASK-871) —
  // the row's own values beat the per-agent /api/presence/agents lookup,
  // which only covers each agent's current-marker session.
  context_pct?: number | null;
  used_tokens?: number | null;
  context_window?: number | null;
}
export interface ActiveSessionsPayload {
  sessions: ActiveSession[];
  counts: Record<string, number>;
  now: number;
  ttl_s: number;
}

export interface HookEvent {
  iso_ts: string;
  hook: string;
  action: string;
  agent: string;
  session_id: string;
  task: string;
}
export interface HooksRecentPayload {
  events: HookEvent[];
  count: number;
}

export interface ChatSession {
  session_id: string;
  summary?: string | null;
  custom_title?: string | null;
  first_prompt?: string | null;
  last_modified?: number | null;
  git_branch?: string | null;
  file_size?: number | null;
}
export interface ChatsPayload {
  sessions: ChatSession[];
}

export interface TraceSession {
  agent: string;
  session_id: string;
  event_count?: number;
  first_event_kind?: string | null;
  mtime_ts?: number;
  source?: string;
  is_active?: boolean;
}
export interface TracesPayload {
  sessions: TraceSession[];
  count: number;
  trace_count: number;
  session_count: number;
}

export interface CostRow {
  formula_id: string;
  day: string;
  total_cost_usd: number;
  count: number;
}
export interface CostPayload {
  rows: CostRow[];
  total_usd: number;
  count: number;
}

export interface BoardListPayload {
  cards: { id: string; title?: string; status?: string; swimlane?: string }[];
  wip?: { counts: Record<string, number>; caps: Record<string, number> };
}

export interface SettingsPayload {
  settings: {
    budget_cap?: { enabled: boolean; cap_usd: number };
  };
}
