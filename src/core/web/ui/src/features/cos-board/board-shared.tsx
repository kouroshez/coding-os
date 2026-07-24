import { createContext, useContext, type CSSProperties } from 'react';
import type {
  AgentPresence,
  BoardAgentManifestEntry,
  BoardConfigPayload,
  SwimlaneDTO,
} from './types';
import type { LiveSessionInfo } from './agentPresenceVisuals';

// Shared board types, constants, colour helpers, and React contexts used by
// CosBoardPage and every extracted board sub-component.

export type HighlightKind = 'kind' | 'swim' | 'priority';
export interface Highlight {
  type: HighlightKind;
  value: string;
}

export interface TaskCounts {
  kind: Record<string, number>;
  swim: Record<string, number>;
  priority: Record<string, number>;
}

export interface CreateTaskForm {
  title: string;
  swimlane: string;
  kind: string;
  priority: string;
  appetite: string;
  epic?: string | null;
  labels?: string[];
  outcome?: string | null;
}

export interface CreateTaskResponse {
  task_id?: string;
  data?: { task_id?: string };
}

// Column ordering matches the Scrumban state machine in
// core/board_os/workflow.py::_VALID_TRANSITIONS. `tint` is the column accent;
// `sub` is the one-line "what this column is".
export const COLUMN_META: Record<string, { label: string; sub: string; wip: number | null; tint: string }> = {
  icebox: { label: 'ICE BOX', sub: 'backlog — tag “ready” to pull', wip: null, tint: '#7c8aa5' },
  emergency: { label: 'EMERGENCY', sub: 'incident fast-lane — skips the queue', wip: 2, tint: '#c0392b' },
  in_progress: { label: 'IN PROGRESS', sub: 'being built right now', wip: 1, tint: '#d97c2c' },
  testing: { label: 'TESTING', sub: 'verifying acceptance (G/W/T)', wip: 3, tint: '#2c7bd9' },
  blocked: { label: 'BLOCKED', sub: 'waiting on an external dep', wip: null, tint: '#8e44ad' },
  complete: { label: 'COMPLETE', sub: 'acceptance met — done', wip: null, tint: '#2e9e5b' },
  archive: { label: 'ARCHIVE', sub: 'frozen cold store', wip: null, tint: '#9aa0a6' },
};

// Fallback when GET /api/board/list has no `agent_manifest` (older Hub).
// `system` = unattended kernel maintenance — an actor for attribution, not a
// presence-bearing agent, so pill rows filter it out (isPresenceAgent).
export const FALLBACK_AGENT_MANIFEST: BoardAgentManifestEntry[] = [
  { id: 'claude', color: '#d97706', label: 'claude', glyph: 'Cl', session: 'ses-claude' },
  { id: 'codex', color: '#0891b2', label: 'codex', glyph: 'Cx', session: 'ses-codex' },
  { id: 'human', color: '#16a34a', label: 'human', glyph: 'H', session: 'local-mac' },
  { id: 'system', color: '#64748b', label: 'system', glyph: 'Sy', session: 'ses-system' },
];

export function isPresenceAgent(entry: BoardAgentManifestEntry): boolean {
  return entry.id !== 'system';
}

export const AgentCatalogContext = createContext<BoardAgentManifestEntry[]>(FALLBACK_AGENT_MANIFEST);

export function useAgentCatalog(): BoardAgentManifestEntry[] {
  return useContext(AgentCatalogContext);
}

// sid → live presence state (active/working only). Card pips pulse from it and
// deep-link to the session's chat; SSE presence bumps keep it fresh.
export const LiveSessionsContext = createContext<ReadonlyMap<string, LiveSessionInfo>>(new Map());

export const EVENT_COLOR: Record<string, string> = {
  'task-updated': '#7c3aed',
  'task-created': '#16a34a',
  'human-move': '#d97706',
  'human-create': '#16a34a',
  connected: '#0891b2',
  agent: '#0891b2',
};

export const EVENT_LABEL: Record<string, string> = {
  'task-updated': 'update',
  'task-created': 'create',
  'human-move': 'drag',
  'human-create': 'create',
  connected: 'sse',
  agent: 'agent',
};

/** Parse #rgb or #rrggbb into [r, g, b] 0..255, or null. */
export function parseHex(hex: string): [number, number, number] | null {
  const s = hex.replace('#', '').trim();
  if (s.length === 3) {
    const r = parseInt(s[0] + s[0], 16);
    const g = parseInt(s[1] + s[1], 16);
    const b = parseInt(s[2] + s[2], 16);
    return Number.isFinite(r + g + b) ? [r, g, b] : null;
  }
  if (s.length === 6) {
    const r = parseInt(s.slice(0, 2), 16);
    const g = parseInt(s.slice(2, 4), 16);
    const b = parseInt(s.slice(4, 6), 16);
    return Number.isFinite(r + g + b) ? [r, g, b] : null;
  }
  return null;
}

export function rgbToHex(r: number, g: number, b: number): string {
  const to = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
  return `#${to(r)}${to(g)}${to(b)}`;
}

/** Darken a hex colour by `pct` (0..1). Used when config.accent === config.color. */
export function darken(hex: string, pct: number): string {
  const rgb = parseHex(hex);
  if (!rgb) return hex;
  const [r, g, b] = rgb;
  const f = 1 - pct;
  return rgbToHex(r * f, g * f, b * f);
}

/** rgba(r,g,b,a) string for a hex colour; a in 0..1. */
export function alpha(hex: string, a: number): string {
  const rgb = parseHex(hex);
  if (!rgb) return hex;
  const [r, g, b] = rgb;
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

/**
 * Given the SwimlaneDTO from the backend, return the palette pair we render:
 * `color` (row tint / band fill) and `accent` (text / border). If config didn't
 * supply a distinct accent we darken the primary colour by ~30% for contrast.
 */
export function lanePalette(lane: SwimlaneDTO): { color: string; accent: string } {
  const color = lane.color || '#6b7280';
  const accent = lane.accent && lane.accent !== lane.color ? lane.accent : darken(color, 0.3);
  return { color, accent };
}

export function columnWipCap(colId: string, wip: BoardConfigPayload['wip_limits'] | undefined): number | null {
  if (wip) {
    if (colId === 'in_progress') return wip.in_progress;
    if (colId === 'testing') return wip.testing;
    if (colId === 'emergency') return wip.emergency;
  }
  return COLUMN_META[colId]?.wip ?? null;
}

export function priorityStyle(priority: string): CSSProperties {
  // Calm + themed: only P0/P1 carry a single thin outline; P2/P3 rely on the
  // priority text badge so the board isn't a wall of red/orange frames.
  switch (priority) {
    case 'P0':
      return { outline: '1.5px solid var(--cos-err)', outlineOffset: 1 };
    case 'P1':
      return { outline: '1px solid var(--cos-warn)' };
    default:
      return {};
  }
}

// AgentState reuses the AgentPresence alias so backend and frontend agree on
// spelling. Visual mapping lives in agentPresenceVisuals.ts.
export type AgentState = AgentPresence;
