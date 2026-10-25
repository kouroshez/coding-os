// ─────────────────────────────────────────────────────────────────────────
// Types — minimal slice of each upstream payload that the dashboard reads.
// ─────────────────────────────────────────────────────────────────────────

// Producer: /api/presence/agents (presence.py::presence_agents) — the
// context-window fill the hub-architecture spec documents.
export interface ContextAgent {
  agent: string;
  session_id?: string | null;
  context_pct: number | null;
  used_tokens?: number | null;
  context_window?: number | null;
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
  // Per-session context fill stamped by /api/sessions/active —
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

export interface BoardListPayload {
  cards: {
    id: string;
    title?: string;
    status?: string;
    swimlane?: string;
    status_dwell_human?: string | null;
  }[];
  wip?: { counts: Record<string, number>; caps: Record<string, number> };
}

