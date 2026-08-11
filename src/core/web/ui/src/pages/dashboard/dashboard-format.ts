// Display tokens + time formatters shared by the dashboard panels.

// ─────────────────────────────────────────────────────────────────────────
// Visual tokens
// ─────────────────────────────────────────────────────────────────────────

export const STATE_DOT: Record<string, { color: string; pulse: boolean; label: string }> = {
  active: { color: '#16a34a', pulse: true, label: 'active' },
  working: { color: '#16a34a', pulse: true, label: 'working' },
  present: { color: '#fbbf24', pulse: false, label: 'present' },
  idle: { color: '#fbbf24', pulse: false, label: 'idle' },
  offline: { color: '#6b7280', pulse: false, label: 'offline' },
};

// Every badge: a faint themed tint bg + the solid hue as text (AA-verified
// in both themes via scripts/badge_contrast.py). Neutral statuses get a
// visible border-tint, never bg=panel. `label` overrides the rendered text
// so long action names aren't clipped.
export const NEUTRAL_BADGE = { bg: 'bg-[var(--cos-border)]/40', text: 'text-[var(--cos-muted)]' };
export const ACTION_BADGE: Record<string, { bg: string; text: string; label?: string }> = {
  fire: { bg: 'bg-[var(--cos-info-tint)]', text: 'text-[var(--cos-info)]' },
  block: { bg: 'bg-[var(--cos-err-tint)]', text: 'text-[var(--cos-err)]' },
  warn: { bg: 'bg-[var(--cos-warn-tint)]', text: 'text-[var(--cos-warn)]' },
  'stale-gate': { bg: 'bg-[var(--cos-warn-tint)]', text: 'text-[var(--cos-warn)]', label: 'stale' },
  skip: { ...NEUTRAL_BADGE },
  'skip-not-replace': { ...NEUTRAL_BADGE, label: 'skip' },
  pass: { bg: 'bg-[var(--cos-ok-tint)]', text: 'text-[var(--cos-ok)]' },
  ok: { bg: 'bg-[var(--cos-ok-tint)]', text: 'text-[var(--cos-ok)]' },
  entry: { bg: 'bg-[var(--cos-brand-tint)]', text: 'text-[var(--cos-brand-text)]' },
  enter: { bg: 'bg-[var(--cos-brand-tint)]', text: 'text-[var(--cos-brand-text)]' },
  dispatched: { bg: 'bg-[var(--cos-live-tint)]', text: 'text-[var(--cos-live)]', label: 'disp' },
  'session-end': { ...NEUTRAL_BADGE, label: 'end' },
  posttooluse: { bg: 'bg-[var(--cos-brand-tint)]', text: 'text-[var(--cos-brand-text)]', label: 'post' },
  pretooluse: { bg: 'bg-[var(--cos-brand-tint)]', text: 'text-[var(--cos-brand-text)]', label: 'pre' },
  'non-rename': { ...NEUTRAL_BADGE, label: 'keep' },
};

// ─────────────────────────────────────────────────────────────────────────
// Format helpers
// ─────────────────────────────────────────────────────────────────────────

export function rel(ms: number | null | undefined): string {
  if (!ms) return '';
  const diff = (Date.now() - ms) / 1000;
  if (diff < 1) return 'now';
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export function relIso(iso: string | null | undefined): string {
  if (!iso) return '';
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? rel(ms) : '';
}

export function ageBadge(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return '';
  return rel(epochSeconds * 1000);
}

export function compactSession(sid?: string | null): string {
  if (!sid) return '';
  if (sid.startsWith('ses-')) return sid.split('-').slice(-2).join('-');
  return sid.slice(0, 8);
}

