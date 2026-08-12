// Pure display helpers for the Memory page. No React, no fetching — every
// function here is a value → label mapping the components can render directly.

import type { PatternRow } from './memory-types';

// 'stat' rows are success-rate baselines (observability), never lessons —
// _learning_extract.py mints them with memory_type='stat' and the digest and
// cos_learn_suggest both exclude them.
export function isStat(p: PatternRow): boolean {
  return p.memory_type === 'stat';
}

export function isPromoted(p: PatternRow): boolean {
  return !!p.promoted_to && p.promoted_to !== 'archived';
}

export function isArchived(p: PatternRow): boolean {
  return p.promoted_to === 'archived';
}

// Where a lesson came from — the producer's source vocabulary
// (_learning_store.py::_SOURCE_TO_PROVENANCE). An unrecognised value renders
// its raw string so a newly added producer source stays visible.
const SOURCE_COPY: Record<string, { label: string; blurb: string }> = {
  friction: {
    label: 'Friction',
    blurb: 'mined from blocked actions and errors the agent hit repeatedly while working',
  },
  breakthrough: {
    label: 'Breakthrough',
    blurb: 'a non-obvious insight the agent recorded itself during a session',
  },
  learn_extract: {
    label: 'Outcome scan',
    blurb: 'distilled by the corpus scan over finished task outcomes',
  },
  commit: { label: 'Commit', blurb: 'derived from what commits actually changed' },
  manual: { label: 'Manual', blurb: 'entered directly by a user directive' },
  import: { label: 'Imported', blurb: 'imported from another project' },
};

export const UNKNOWN_SOURCE = 'unknown';

export function sourceCopy(source: string | null): { label: string; blurb: string } {
  if (!source) return { label: 'No source recorded', blurb: 'the producer left this row unattributed' };
  return SOURCE_COPY[source] ?? { label: source, blurb: 'source reported by the producer' };
}

// memory_type as the producer stores it. Rendered verbatim when unmapped so a
// new type is never silently swept into the "lesson" framing.
const TYPE_COPY: Record<string, string> = {
  lesson: 'lesson',
  error: 'error',
  failure: 'failure',
  pattern: 'pattern',
  stat: 'stat',
  workflow: 'workflow',
  decision: 'decision',
  discovery: 'discovery',
};

export function typeLabel(memoryType: string): string {
  return TYPE_COPY[memoryType] ?? memoryType;
}

// Confidence is system-computed by LTP/LTD (src/core/rules/memory.md) — never
// hand-set — so it gets a word next to the number instead of a bare bar.
export function confidenceBand(confidence: number): { label: string; token: string } {
  if (confidence >= 0.7) return { label: 'strong', token: 'var(--cos-ok)' };
  if (confidence >= 0.45) return { label: 'moderate', token: 'var(--cos-info)' };
  return { label: 'weak', token: 'var(--cos-warn)' };
}

export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

// SQLite timestamps arrive as "YYYY-MM-DD HH:MM:SS" (no zone) or ISO-8601.
// Both parse; anything else renders as an em dash rather than "Invalid Date".
export function ageLabel(iso: string | null | undefined): string {
  if (!iso) return '—';
  const then = new Date(iso.includes('T') ? iso : iso.replace(' ', 'T')).getTime();
  if (Number.isNaN(then)) return '—';
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days < 0) return 'just now';
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  if (days < 60) return `${Math.floor(days / 7)}w ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

export function dateLabel(iso: string | null | undefined): string {
  if (!iso) return 'never';
  const d = new Date(iso.includes('T') ? iso : iso.replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? 'never' : d.toLocaleString();
}

// Only Trusted / Fading carry information — every row is Forming until a
// session validates it, so a "Forming" badge on every card is pure noise.
export function tierStyle(tier: string): { bg: string; fg: string } | null {
  if (tier === 'Trusted') return { bg: 'var(--cos-ok-tint)', fg: 'var(--cos-ok)' };
  if (tier === 'Fading') return { bg: 'var(--cos-warn-tint)', fg: 'var(--cos-warn)' };
  return null;
}

// Split ANY producer lesson format on the " → " separator: left = situation
// (what happened), right = action (what to do). Covers all 4 shapes —
// "Recurring <kind> (N occurrences): …", "Fixed repeatedly (N occurrences): …",
// "Reverted before: …", and arrow-less ([Breakthrough] …) → whole text, no action.
export function splitLesson(pattern: string): { situation: string; action: string | null } {
  const arrow = pattern.lastIndexOf(' → ');
  if (arrow === -1) return { situation: pattern, action: null };
  const action = pattern.slice(arrow + 3).trim();
  const situation = pattern
    .slice(0, arrow)
    .trim()
    .replace(/^(Recurring [a-z ]+|Fixed repeatedly)\s*\(\d+ occurrences?\):\s*/i, '');
  return { situation: situation || pattern.slice(0, arrow).trim(), action };
}

// Distilled lessons store the sanitized failure samples that justified them.
export function evidenceSamples(p: PatternRow): string[] {
  if (!p.evidence_json) return [];
  try {
    const parsed = JSON.parse(p.evidence_json) as { samples?: unknown };
    if (Array.isArray(parsed.samples)) return parsed.samples.map(String).slice(0, 3);
  } catch {
    /* malformed evidence is not worth an error surface */
  }
  return [];
}
