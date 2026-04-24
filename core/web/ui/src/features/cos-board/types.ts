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

export type AgentPresence = 'active' | 'present' | 'offline';

export interface BoardListPayload {
  grouped: Record<string, Record<string, BoardListCard[]>>;
  cards: BoardListCard[];
  count: number;
  wip?: {
    counts: Record<string, number>;
    caps: Record<string, number>;
    violations: string[];
  } | null;
  /** Back-compat list of "not offline" agents (pre-0.5 consumers). */
  active_agents?: string[];
  /** Preferred signal: per-agent presence state. */
  agent_states?: Record<string, AgentPresence>;
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
};
