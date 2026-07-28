import { useEffect, useId, useState } from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries } from '@/lib/hooks';

// Shared table chrome + config-mutation helpers used by every ConfigPage tab.

export function TabIntro({ children }: { children: ReactNode }) {
  return <p className="mb-4 text-sm text-[var(--cos-muted)]">{children}</p>;
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--cos-border)]">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-[var(--cos-border)] bg-[var(--cos-panel)]/60">
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-semibold tracking-wide text-[var(--cos-muted)]">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Pill({ tone, children }: { tone: 'ok' | 'muted'; children: ReactNode }) {
  const cls =
    tone === 'ok'
      ? 'border-[var(--cos-ok)] bg-[var(--cos-ok-tint)] text-[var(--cos-ok)]'
      : 'border-[var(--cos-border)] text-[var(--cos-muted)]';
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium ${cls}`}>{children}</span>;
}

export function StateRow({ children }: { children: ReactNode }) {
  return <p className="px-1 py-6 text-sm text-[var(--cos-muted)]">{children}</p>;
}

// The meta-repo's own derived slug (cli.registry._derive_slug). Mutations are
// disabled on this slug; the Git tab keys its trunk caution off the same value.
export const META_REPO_SLUG = 'coding-os';

export function useConfigMutation(invalidate: string[]) {
  const qc = useQueryClient();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async <T,>(id: string, fn: () => Promise<T>): Promise<T | null> => {
    setBusyId(id);
    setError(null);
    try {
      const out = await fn();
      for (const key of invalidate) await invalidateApiQueries(qc, key);
      return out;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'operation failed');
      return null;
    } finally {
      setBusyId(null);
    }
  };
  return { busyId, error, setError, run };
}

export function SectionCard({
  title,
  subtitle,
  count,
  action,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  count?: number;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mb-5 overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40">
      <header className="flex items-center justify-between gap-3 border-b border-[var(--cos-border)] px-4 py-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--cos-text)]">
            {title}
            {typeof count === 'number' && (
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-normal text-[var(--cos-muted)]">
                {count}
              </span>
            )}
          </h3>
          {subtitle && (
            <p className="mt-0.5 max-w-2xl text-[11px] leading-relaxed text-[var(--cos-faint)]">{subtitle}</p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      <div className="divide-y divide-[var(--cos-border)]">{children}</div>
    </section>
  );
}

export function ConfigRow({
  title,
  badges,
  meta,
  action,
}: {
  title: ReactNode;
  badges?: ReactNode;
  meta?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-white/[0.02]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium text-[var(--cos-text)]">{title}</span>
          {badges}
        </div>
        {meta && <div className="mt-0.5 text-[11px] leading-relaxed text-[var(--cos-faint)]">{meta}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function EmptyRow({ children }: { children: ReactNode }) {
  return <p className="px-4 py-6 text-center text-[13px] text-[var(--cos-muted)]">{children}</p>;
}

export function CfgButton({
  tone = 'ghost',
  busy,
  disabled,
  onClick,
  icon,
  title,
  ariaPressed,
  children,
}: {
  tone?: 'primary' | 'ghost' | 'danger';
  busy?: boolean;
  disabled?: boolean;
  onClick: () => void;
  icon?: ReactNode;
  title?: string;
  ariaPressed?: boolean;
  children: ReactNode;
}) {
  const palette =
    tone === 'primary'
      ? 'border-transparent bg-[var(--cos-accent-solid)] text-white hover:opacity-90'
      : tone === 'danger'
        ? 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-err)] hover:text-[var(--cos-err)]'
        : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-accent)] hover:text-[var(--cos-text)]';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      title={title}
      aria-pressed={ariaPressed}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:cursor-not-allowed disabled:opacity-40 ${palette}`}
    >
      {busy ? <span className="animate-pulse">…</span> : icon}
      {children}
    </button>
  );
}

// Accessible ⓘ popover. Opens on hover AND click/focus, closes on Esc,
// keyboard-reachable.
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const tipId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={`What is ${label}?`}
        aria-describedby={open ? tipId : undefined}
        onClick={() => setOpen((v) => !v)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-[var(--cos-border)] text-[10px] font-semibold leading-none text-[var(--cos-faint)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          id={tipId}
          className="absolute left-0 top-5 z-20 w-72 rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-2 text-[11px] font-normal leading-relaxed text-[var(--cos-muted)] shadow-xl"
        >
          {children}
        </span>
      )}
    </span>
  );
}

// Small toggle/preset pill for branch selection (reused by both branch fields).
export function Chip({
  active,
  onClick,
  children,
  ariaLabel,
}: {
  active?: boolean;
  onClick: () => void;
  children: ReactNode;
  ariaLabel?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      aria-pressed={active}
      className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none ${
        active
          ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/15 text-[var(--cos-text)]'
          : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:text-[var(--cos-text)]'
      }`}
    >
      {children}
    </button>
  );
}

// A field label with an inline InfoTip — used by every Git-tab control.
export function FieldLabel({ label, tip }: { label: ReactNode; tip: ReactNode }) {
  const labelText = typeof label === 'string' ? label : 'this field';
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-xs font-medium text-[var(--cos-muted)]">{label}</span>
      <InfoTip label={labelText}>{tip}</InfoTip>
    </span>
  );
}
