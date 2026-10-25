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

export function ageBadge(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return '';
  return rel(epochSeconds * 1000);
}

export function compactSession(sid?: string | null): string {
  if (!sid) return '';
  if (sid.startsWith('ses-')) return sid.split('-').slice(-2).join('-');
  return sid.slice(0, 8);
}

