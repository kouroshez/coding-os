/**
 * PURPOSE: Single source of truth mapping agent presence states to the
 *          visual attributes the board renders.  Extracted from
 *          CosBoardPage.tsx so the contract is typed, import-safe, and
 *          covered by an exhaustive compile-time check — adding a new
 *          AgentPresence variant without updating the visuals table
 *          becomes a build error, not a silent UI regression.
 * INPUT:   `AgentPresence` value from the backend (`/api/board/list`).
 * OUTPUT:  `{ color, ring, pulse, label }` used by AgentBadge.
 * NOTES:   Colors follow the same traffic-light metaphor the rest of
 *          the board uses: green = hook-confirmed liveness, amber = alive
 *          but idle / DB-inferred, red = gone.
 */
import type { AgentPresence } from './types';

export interface AgentVisual {
  color: string;
  ring: string;
  pulse: boolean;
  label: string;
}

// Exhaustive `Record<AgentPresence, ...>` — TypeScript flags any missing
// variant as an error at build time, which is the lock-in we want.
export const AGENT_PRESENCE_VISUALS: Record<AgentPresence, AgentVisual> = {
  active: {
    color: '#16a34a',
    ring: 'rgba(22,163,74,.30)',
    pulse: true,
    label: 'active',
  },
  // `working` = user turn in flight (prompt > stop, pid alive) but no
  // recent tool call. Distinct hue from `present` so a thinking agent
  // doesn't read as idle.  Cyan/teal — visually unrelated to any
  // adapter brand color (claude amber, codex cyan-blue, cursor indigo).
  working: {
    color: '#45d6e8',
    ring: 'rgba(69,214,232,.30)',
    pulse: true,
    label: 'working',
  },
  present: {
    color: '#eab308',
    ring: 'rgba(234,179,8,.25)',
    pulse: false,
    label: 'present',
  },
  offline: {
    color: '#9ca3af',
    ring: 'rgba(156,163,175,.15)',
    pulse: false,
    label: 'offline',
  },
};

/**
 * Belt-and-braces runtime assertion: if the backend ever sends an
 * unknown presence string (e.g. during a staged backend rollout that
 * adds a new variant), we still render a sane fallback instead of
 * crashing on `undefined.color`.
 */
export function visualFor(state: AgentPresence | string | null | undefined): AgentVisual {
  const v = state ? AGENT_PRESENCE_VISUALS[state as AgentPresence] : undefined;
  return v ?? AGENT_PRESENCE_VISUALS.offline;
}
