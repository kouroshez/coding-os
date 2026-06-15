/** Board card as returned by `/api/board/list` (`id` is task id). */
export interface BoardListCard {
  id: string;
  title: string;
  swimlane: string;
  kind: string;
  epic: string | null;
  labels: string[];
  status: string;
  priority: string;
  appetite?: string;
  agent_session?: string | null;
  last_log_line?: string | null;
}

export type AgentPresence = 'active' | 'working' | 'present' | 'offline';

/** One row in the live-agents strip — from GET /api/board/list `agent_manifest`. */
export interface BoardAgentManifestEntry {
  id: string;
  label: string;
  glyph: string;
  color: string;
  session: string;
}

/** Per-column keyset pagination meta for paged columns (complete/archive). */
export interface BoardColumnMeta {
  total_count?: number;
  returned?: number;
  next_cursor?: string | null;
  truncated?: boolean;
  /** Present on the synthetic `_active` key when active columns were capped. */
  cap?: number;
}

export interface BoardListPayload {
  cards: BoardListCard[];
  count: number;
  /** Total cards across all returned columns (TASK-223). */
  total_count?: number;
  /** True when the agent token-budget cap dropped cards (apply_budget path). */
  truncated?: boolean;
  /** Per-column pagination meta keyed by status; complete/archive carry
   *  next_cursor + total_count for "load more". `_active` carries the
   *  active-columns truncation flag. TASK-223. */
  columns?: Record<string, BoardColumnMeta>;
  wip?: {
    counts: Record<string, number>;
    caps: Record<string, number>;
    violations: string[];
  } | null;
  /** Back-compat list of "not offline" agents (pre-0.5 consumers). */
  active_agents?: string[];
  /** Preferred signal: per-agent presence state. */
  agent_states?: Record<string, AgentPresence>;
  /** P2 — count of live (non-offline) sessions per agent. Drives the
   *  `Cl·3` suffix on the live-agents pill so parallel sessions stop
   *  collapsing into one verdict. */
  session_counts?: Record<string, number>;
  /** P2 — full per-session inventory; tooltip / debug surface. */
  session_states?: Array<{
    agent: string;
    sid: string;
    state: AgentPresence;
    pid: number;
    started_at: number | null;
    last_prompt_at: number | null;
    last_tool_at: number | null;
    last_stop_at: number | null;
  }>;
  /** Adapter ids + Hub pill metadata (includes trailing `human` row). */
  agent_manifest?: BoardAgentManifestEntry[];
  /** Always `per_project` today — global aggregation is documented only. */
  presence_scope?: string;
}

export interface SwimlaneDTO {
  id: string;
  label: string;
  color: string;
  accent: string;
  description: string;
}

export interface ColumnDTO {
  id: string;
  label: string;
}

export interface BoardConfigPayload {
  swimlanes: SwimlaneDTO[];
  columns: ColumnDTO[];
  wip_limits: {
    in_progress: number;
    testing: number;
    emergency: number;
  };
}

export interface BoardTweaks {
  theme: 'light' | 'dark';
  density: 'cozy' | 'compact';
  agentSurface: boolean;
  showWipViolation: boolean;
  filterKind: string;
  filterEpic: string;
  filterSwim: string;
  aesthetic: 'whiteboard' | 'graph' | 'terminal';
  quietMode: boolean;
  /** Archive is a "soft-terminal" cold store; hidden by default so the
   *  main board stays focused on active work.  Flip from the header
   *  toggle to surface it. */
  showArchive: boolean;
  /** Swimlane grid (status × swimlane) is the default. Off collapses the
   *  swimlane dimension into flat status columns so every active task is
   *  visible at a glance without scrolling lanes — each card keeps its
   *  swimlane colour for grouping. */
  showSwimlanes: boolean;
}

export const DEFAULT_TWEAKS: BoardTweaks = {
  theme: 'light',
  density: 'cozy',
  agentSurface: true,
  showWipViolation: true,
  filterKind: 'all',
  filterEpic: 'all',
  filterSwim: 'all',
  // 'whiteboard' keeps the hand-drawn look from the Claude Design prototype:
  // rotated sticky cards + Kalam/Permanent Marker fonts + paper texture.
  // 'graph' is the technical notebook variant (flat cards, grid bg) — opt-in
  // via the Tweaks panel.
  aesthetic: 'whiteboard',
  quietMode: false,
  showArchive: false,
  showSwimlanes: true,
};
