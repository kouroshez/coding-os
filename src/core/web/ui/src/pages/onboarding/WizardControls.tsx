import type * as React from 'react';
import type { SkillEntry } from './wizard-types';

export function ToggleChip({
  active, label, hint, locked, onClick, testId,
}: {
  active: boolean; label: string; hint?: string; locked?: boolean;
  onClick?: () => void; testId?: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={locked}
      aria-pressed={active}
      title={hint}
      className={[
        'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]',
        locked
          ? 'cursor-default border-[var(--cos-border)] bg-[var(--cos-bg)]/40 text-[var(--cos-muted)]'
          : active
            ? 'border-[var(--accent)] bg-[var(--accent)]/12 text-[var(--accent)] shadow-sm'
            : 'border-[var(--cos-border)] bg-[var(--cos-panel)]/60 text-[var(--cos-text)] hover:border-[var(--accent)]/60 hover:text-[var(--accent)]',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function tierBadge(tier: string | null) {
  if (!tier) return null;
  return (
    <span className="rounded bg-[var(--cos-bg)]/60 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-[var(--cos-faint)]">
      {tier}
    </span>
  );
}

export function SkillRow({ entry, action }: { entry: SkillEntry; action?: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 rounded-lg border border-[var(--cos-border)]/70 bg-[var(--cos-bg)]/30 px-2.5 py-2">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <code className="text-xs font-semibold text-[var(--cos-text)]">{entry.name}</code>
          {tierBadge(entry.tier)}
          {entry.domain.slice(0, 3).map((d) => (
            <span key={d} className="rounded bg-[var(--accent)]/10 px-1.5 py-px text-[9px] text-[var(--accent)]">
              {d}
            </span>
          ))}
        </div>
        {entry.description && (
          <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-[var(--cos-muted)]">
            {entry.description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </li>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-[var(--cos-text)]">{label}</span>
      {hint && <span className="mb-1.5 block text-[11px] leading-snug text-[var(--cos-muted)]">{hint}</span>}
      {children}
    </label>
  );
}

