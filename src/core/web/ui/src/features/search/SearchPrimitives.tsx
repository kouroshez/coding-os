import type * as React from 'react';

export function Section({
  title,
  count,
  isLoading,
  error,
  children,
}: {
  title: string;
  count: number;
  isLoading: boolean;
  error: Error | null;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title}>
      <h2 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        <span>{title}</span>
        <span className="rounded bg-[var(--cos-border)]/40 px-1.5 py-0.5 font-mono text-[10px] text-[var(--cos-text)]">{count}</span>
        {isLoading && <span className="text-[10px] normal-case text-[var(--cos-muted)]">loading…</span>}
      </h2>
      {error && (
        <p role="alert" className="mb-2 text-xs text-[var(--cos-err)]">
          {error.message}
        </p>
      )}
      <ul className="space-y-2">{children}</ul>
    </section>
  );
}

export function RowButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={[
          'block w-full rounded-lg border bg-[var(--cos-panel)]/70 p-2.5 text-left text-xs text-[var(--cos-text)] transition-colors',
          active
            ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/5'
            : 'border-[var(--cos-border)] hover:border-[var(--cos-accent)]/60 hover:bg-[var(--cos-panel)]',
        ].join(' ')}
      >
        {children}
      </button>
    </li>
  );
}

export function Tag({ children, muted }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <span
      className={[
        'rounded px-1 py-0.5 text-[10px] uppercase tracking-wide',
        muted
          ? 'bg-[var(--cos-border)]/30 text-[var(--cos-muted)]'
          : 'bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]',
      ].join(' ')}
    >
      {children}
    </span>
  );
}

export function StatusTag({ status }: { status: string }) {
  const palette: Record<string, string> = {
    open: 'bg-[var(--cos-info-tint)] text-[var(--cos-info)]',
    wip: 'bg-[var(--cos-warn-tint)] text-[var(--cos-warn)]',
    in_progress: 'bg-[var(--cos-warn-tint)] text-[var(--cos-warn)]',
    testing: 'bg-[var(--cos-brand-tint)] text-[var(--cos-brand-text)]',
    blocked: 'bg-[var(--cos-err-tint)] text-[var(--cos-err)]',
    done: 'bg-[var(--cos-ok-tint)] text-[var(--cos-ok)]',
  };
  const cls = palette[status] ?? 'bg-[var(--cos-border)]/30 text-[var(--cos-muted)]';
  return <span className={['rounded px-1 py-0.5 text-[10px] uppercase tracking-wide', cls].join(' ')}>{status}</span>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-2 py-3 text-xs text-[var(--cos-muted)]">{children}.</p>;
}
